"""Gemini-based question scraper.

Extracts admission-test questions from an uploaded PDF or DOCX using the Google
Gemini REST API and returns them in the SAME per-item dict shape produced by the
structural DOCX scraper (``mainapp/views/demo_scrapper.py``) so the output can be
fed directly into ``ingest_scraped_question_entries``.

PDF is the preferred input: it is sent to Gemini as inline document data, so
Gemini reads the *rendered* pages with its vision stack. That means Bijoy/ANSI
Bangla fonts (which have no clean Unicode text layer) are handled correctly.
DOCX is supported by extracting its text with python-docx and passing it as
text — fine for Unicode DOCX, but for Bijoy DOCX prefer exporting to PDF first.
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from typing import Any

import requests

try:  # python-docx is already a project dependency
    from docx import Document
    from lxml import etree

    _HAS_PYDOCX = True
except Exception:  # pragma: no cover - defensive
    _HAS_PYDOCX = False


GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Keep this comfortably below Gemini's inline-data limit (~20MB request).
MAX_INLINE_PDF_BYTES = 18 * 1024 * 1024

REQUEST_TIMEOUT = 170  # seconds; the view/frontend allow a longer window


PROMPT = r"""You are an expert exam-question extractor for a university admission test.
You are given a document (PDF pages or extracted DOCX text) that contains
multiple-choice and/or written questions. Some Bangla text may be rendered with
the "Bijoy" ANSI font — read the VISUAL content of the pages, not any garbled
text layer.

Return ONLY a JSON array (no markdown, no commentary). Each element is one
question object with EXACTLY these keys:

{
  "subject": string,              // e.g. "Mathematics" (from the header)
  "question_bangla": string,      // Bangla question text, "" if none
  "question_english": string,     // English question text, "" if none
  "question_both": string,        // combined "bangla (english)" or whichever exists
  "options": {
    "both":    { "ক": string, "খ": string, "গ": string, "ঘ": string },
    "english": { "A": string, "B": string, "C": string, "D": string }
  },
  "answer": {
    "both":    [ "<one of ক/খ/গ/ঘ>" ],
    "english": [ "<one of A/B/C/D>" ]
  },
  "semester": string,             // e.g. "Spring 2024" (from the header)
  "department": string,           // e.g. "CSE"; use "CSE" if unknown
  "qno": number                   // the printed question number
}

STRICT RULES:
- ALWAYS provide BOTH "question_bangla" and "question_english". If the source has
  the question in only ONE language, TRANSLATE it to produce the other language so
  neither field is empty (unless the question is purely a formula/math with no
  words, in which case both may hold the same math). "question_both" =
  "<bangla> (<english>)".
- For a multiple-choice question, fill BOTH option sets and keep them complete:
    * "both"    -> EXACTLY 4 options keyed ক, খ, গ, ঘ (Bangla version).
    * "english" -> EXACTLY 4 options keyed A, B, C, D (English version).
  First option -> ক/A, second -> খ/B, third -> গ/C, fourth -> ঘ/D, regardless of
  how the printed option letters look (K/L/M/N, ক/খ/গ/ঘ, a/b/c/d …).
  If an option exists in only one language, TRANSLATE it to fill the other set.
  Pure math/number/LaTeX options are identical in both sets (do NOT translate math;
  keep the $...$ content byte-for-byte the same in "both" and "english").
- "answer" must contain the KEY of the correct option, not its text. Map the
  answer-sheet letter to option POSITION: 1st->ক/A, 2nd->খ/B, 3rd->গ/C, 4th->ঘ/D.
  Fill BOTH answer.both (ক/খ/গ/ঘ) and answer.english (A/B/C/D) with the SAME
  position. Use the answer key printed in the document if present.
- The "subject" field stays in English exactly as printed (e.g. "Mathematics").
  Do NOT translate the subject and do NOT create a Bangla version of it.
- For a written/non-MCQ question, use empty option objects {} and empty answer
  lists []; put the full question (in both languages, translating if needed) in
  the question fields.
- MATH: wrap every mathematical expression, formula, equation, matrix, fraction,
  power, integral, limit, or symbol in inline LaTeX delimited by single dollar
  signs, e.g. "$x^3 - 4x^2 - x + 4 = 0$", "$\int_{-1}^{1} 3x^2\,dx$",
  "$\begin{vmatrix} 1 & 2 & 3 \\ 4 & 5 & 6 \\ 7 & 8 & 9 \end{vmatrix}$".
  Apply this inside question text AND option text.
- If the provided DOCUMENT TEXT already contains math wrapped in $...$ LaTeX,
  KEEP it verbatim and place each piece with the correct question/option — do not
  drop it. Every question and option that had math MUST retain its $...$ content.
- Do not invent questions. Extract exactly what is in the document.
"""


class GeminiScrapeError(Exception):
    """Raised when the Gemini request or its response cannot be processed."""


# OOXML namespaces
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

# Map n-ary operators to LaTeX commands.
_NARY_OPS = {
    "∫": r"\int",
    "∬": r"\iint",
    "∭": r"\iiint",
    "∮": r"\oint",
    "∑": r"\sum",
    "∏": r"\prod",
    "∐": r"\coprod",
    "⋃": r"\bigcup",
    "⋂": r"\bigcap",
}


def _localname(el) -> str:
    return etree.QName(el).localname


def _m_children(el, name: str) -> list:
    """Direct math-namespace children with the given local name."""
    return [c for c in el.iterchildren() if _localname(c) == name and etree.QName(c).namespace == M_NS]


def _m_child(el, name: str):
    kids = _m_children(el, name)
    return kids[0] if kids else None


def _seq_to_latex(el) -> str:
    """Convert the sequence of math child nodes of `el` to LaTeX."""
    return "".join(_omml_to_latex(child) for child in el.iterchildren())


def _omml_to_latex(el) -> str:  # noqa: C901 - a dispatch tree, kept flat on purpose
    """Best-effort conversion of an OMML element to inline LaTeX."""
    if etree.QName(el).namespace != M_NS:
        # non-math node inside math (rare) — pull any text
        return "".join(t.text or "" for t in el.findall(f".//{{{M_NS}}}t"))

    tag = _localname(el)

    if tag == "t":  # math text run content
        return el.text or ""
    if tag in {"oMath", "oMathPara", "e", "num", "den", "deg", "sub", "sup", "fName", "lim"}:
        return _seq_to_latex(el)
    if tag == "r":  # math run: gather m:t children
        return "".join(t.text or "" for t in _m_children(el, "t"))

    if tag == "sSup":  # base^{sup}
        base = _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""
        sup = _seq_to_latex(_m_child(el, "sup")) if _m_child(el, "sup") is not None else ""
        return f"{base}^{{{sup}}}"
    if tag == "sSub":  # base_{sub}
        base = _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""
        sub = _seq_to_latex(_m_child(el, "sub")) if _m_child(el, "sub") is not None else ""
        return f"{base}_{{{sub}}}"
    if tag == "sSubSup":  # base_{sub}^{sup}
        base = _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""
        sub = _seq_to_latex(_m_child(el, "sub")) if _m_child(el, "sub") is not None else ""
        sup = _seq_to_latex(_m_child(el, "sup")) if _m_child(el, "sup") is not None else ""
        return f"{base}_{{{sub}}}^{{{sup}}}"
    if tag == "f":  # fraction
        num = _seq_to_latex(_m_child(el, "num")) if _m_child(el, "num") is not None else ""
        den = _seq_to_latex(_m_child(el, "den")) if _m_child(el, "den") is not None else ""
        return f"\\frac{{{num}}}{{{den}}}"
    if tag == "rad":  # radical / root
        deg_el = _m_child(el, "deg")
        base = _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""
        deg = _seq_to_latex(deg_el) if deg_el is not None else ""
        return f"\\sqrt[{deg}]{{{base}}}" if deg.strip() else f"\\sqrt{{{base}}}"
    if tag == "nary":  # integral / sum / product with limits
        pr = _m_child(el, "naryPr")
        chr_char = "∫"
        if pr is not None:
            chr_el = _m_child(pr, "chr")
            if chr_el is not None:
                chr_char = chr_el.get(f"{{{M_NS}}}val") or chr_char
        op = _NARY_OPS.get(chr_char, r"\int")
        sub = _seq_to_latex(_m_child(el, "sub")) if _m_child(el, "sub") is not None else ""
        sup = _seq_to_latex(_m_child(el, "sup")) if _m_child(el, "sup") is not None else ""
        base = _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""
        limits = ""
        if sub.strip():
            limits += f"_{{{sub}}}"
        if sup.strip():
            limits += f"^{{{sup}}}"
        return f"{op}{limits} {base}"
    if tag == "d":  # delimiter, e.g. (...), |...| for determinants
        pr = _m_child(el, "dPr")
        beg, end = "(", ")"
        if pr is not None:
            beg_el = _m_child(pr, "begChr")
            end_el = _m_child(pr, "endChr")
            if beg_el is not None:
                beg = beg_el.get(f"{{{M_NS}}}val") or beg
            if end_el is not None:
                end = end_el.get(f"{{{M_NS}}}val") or end
        inner = "".join(_seq_to_latex(e) for e in _m_children(el, "e"))
        return f"\\left{beg} {inner} \\right{end}"
    if tag == "m":  # matrix
        rows = []
        for mr in _m_children(el, "mr"):
            cells = [_seq_to_latex(e) for e in _m_children(mr, "e")]
            rows.append(" & ".join(cells))
        body = " \\\\ ".join(rows)
        return f"\\begin{{matrix}} {body} \\end{{matrix}}"
    if tag == "func":  # named function, e.g. sin(x)
        name = _seq_to_latex(_m_child(el, "fName")) if _m_child(el, "fName") is not None else ""
        arg = _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""
        return f"{name}{arg}"
    if tag == "acc":  # accent
        return _seq_to_latex(_m_child(el, "e")) if _m_child(el, "e") is not None else ""

    # Fallback: recurse into children so nested text is not lost.
    return _seq_to_latex(el)


def _paragraph_to_text(p_elem) -> str:
    """Serialize a <w:p> to text, converting inline OMML equations to $...$ LaTeX."""
    parts: list[str] = []
    for child in p_elem.iterchildren():
        ns = etree.QName(child).namespace
        name = _localname(child)
        if ns == M_NS and name in {"oMath", "oMathPara"}:
            if name == "oMathPara":
                for om in _m_children(child, "oMath"):
                    latex = _omml_to_latex(om).strip()
                    if latex:
                        parts.append(f"${latex}$")
            else:
                latex = _omml_to_latex(child).strip()
                if latex:
                    parts.append(f"${latex}$")
        else:
            # ordinary run(s) / hyperlinks / etc. — collect w:t text in document order
            texts = child.findall(f".//{{{W_NS}}}t")
            if texts:
                parts.append("".join(t.text or "" for t in texts))
    return "".join(parts)


def _docx_to_text(file_bytes: bytes) -> str:
    if not _HAS_PYDOCX:
        raise GeminiScrapeError("python-docx is not installed on the server")
    document = Document(BytesIO(file_bytes))

    parts: list[str] = []
    for paragraph in document.paragraphs:
        line = _paragraph_to_text(paragraph._p).strip()
        if line:
            parts.append(line)

    for table in document.tables:
        for row in table.rows:
            cells = []
            for cell in row.cells:
                cell_text = " ".join(
                    _paragraph_to_text(p._p).strip() for p in cell.paragraphs
                ).strip()
                if cell_text:
                    cells.append(cell_text)
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def _build_parts(file_bytes: bytes, filename: str, mimetype: str) -> list[dict[str, Any]]:
    """Build the Gemini `contents[0].parts` list for the given file."""
    name = (filename or "").lower()
    is_pdf = name.endswith(".pdf") or (mimetype or "").lower() == "application/pdf"

    parts: list[dict[str, Any]] = [{"text": PROMPT}]

    if is_pdf:
        if len(file_bytes) > MAX_INLINE_PDF_BYTES:
            raise GeminiScrapeError(
                "PDF is too large to process inline (max ~18MB). "
                "Please split it into smaller files."
            )
        parts.append(
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": base64.b64encode(file_bytes).decode("ascii"),
                }
            }
        )
    else:
        text = _docx_to_text(file_bytes)
        if not text.strip():
            raise GeminiScrapeError("No extractable text found in the DOCX file")
        parts.append({"text": "DOCUMENT TEXT:\n" + text})

    return parts


def _extract_json_array(text: str) -> list[Any]:
    """Parse a JSON array out of the model's text response, tolerating stray wrappers."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        # strip ```json ... ``` fences if the model added them
        cleaned = cleaned.strip("`")
        newline = cleaned.find("\n")
        if newline != -1 and cleaned[:newline].strip().lower() in {"json", ""}:
            cleaned = cleaned[newline + 1 :]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise GeminiScrapeError("Gemini response did not contain a JSON array")
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GeminiScrapeError(f"Could not parse Gemini JSON response: {exc}") from exc

    if isinstance(parsed, dict):
        # tolerate {"questions": [...]} or {"data": [...]}
        for key in ("questions", "data", "results"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        raise GeminiScrapeError("Gemini returned an object without a question array")
    if not isinstance(parsed, list):
        raise GeminiScrapeError("Gemini response was not a JSON array")
    return parsed


def _normalize_item(item: Any, index: int) -> dict[str, Any]:
    """Coerce a single Gemini item into the ingestion per-item shape (defensively)."""
    if not isinstance(item, dict):
        return {}

    options = item.get("options") if isinstance(item.get("options"), dict) else {}
    answer = item.get("answer") if isinstance(item.get("answer"), dict) else {}

    both_opts = options.get("both") if isinstance(options.get("both"), dict) else {}
    eng_opts = options.get("english") if isinstance(options.get("english"), dict) else {}

    def _as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if value in (None, ""):
            return []
        return [str(value).strip()]

    return {
        "subject": str(item.get("subject") or "").strip(),
        "question_bangla": str(item.get("question_bangla") or "").strip(),
        "question_english": str(item.get("question_english") or "").strip(),
        "question_both": str(item.get("question_both") or "").strip(),
        "options": {"both": both_opts, "english": eng_opts},
        "answer": {"both": _as_list(answer.get("both")), "english": _as_list(answer.get("english"))},
        "semester": str(item.get("semester") or "").strip(),
        "department": str(item.get("department") or "CSE").strip() or "CSE",
        "qno": item.get("qno") if isinstance(item.get("qno"), int) else (index + 1),
    }


def scrape_with_gemini(
    file_bytes: bytes,
    filename: str,
    mimetype: str,
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """Send the file to Gemini and return questions in the ingestion per-item shape.

    Raises ``GeminiScrapeError`` on any request/parse failure with a user-safe message.
    """
    if not api_key:
        raise GeminiScrapeError("Gemini API key is required")
    if not file_bytes:
        raise GeminiScrapeError("Uploaded file is empty")

    model = (model or "gemini-3.5-flash").strip()
    parts = _build_parts(file_bytes, filename, mimetype)

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    }

    url = GEMINI_ENDPOINT.format(model=model)
    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GeminiScrapeError(f"Could not reach Gemini API: {exc}") from exc

    if response.status_code != 200:
        message = response.text
        try:
            err = response.json().get("error", {})
            message = err.get("message", message)
        except Exception:
            pass
        raise GeminiScrapeError(f"Gemini API error ({response.status_code}): {message}")

    try:
        body = response.json()
        candidates = body.get("candidates") or []
        if not candidates:
            feedback = body.get("promptFeedback") or {}
            reason = feedback.get("blockReason")
            raise GeminiScrapeError(
                f"Gemini returned no content{f' (blocked: {reason})' if reason else ''}"
            )
        text_parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = "".join(part.get("text", "") for part in text_parts)
    except GeminiScrapeError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise GeminiScrapeError(f"Unexpected Gemini response format: {exc}") from exc

    items = _extract_json_array(raw_text)
    return [normalized for i, item in enumerate(items) if (normalized := _normalize_item(item, i))]
