#!/usr/bin/env python3
"""
Improved Bangla+English admission Q/A scraper.

Fixes:
- Prevents English text from "leaking" into options by using STRICT option labels.
- Accepts Bangla labels: (ক) or bare token forms "ক)" / "ক." / "ক:" ONLY at token boundaries.
- Accepts English text embedded in Bangla stems: returns question_bangla + question_english.
- Stronger Subject/Session/Department extraction with filename fallback (e.g., ...-CSE.docx).
- Maps answers from a 2-row table OR vertical "Answer:" list, and normalizes to both (খ) and (B).
- CLI included for quick manual tests: interactive if no args, or use flags (--summary, --stdout, -o).

JSON schema preserved:
{
  "subject": str,
  "question_bangla": str,
  "question_english": str,
  "options": [{"bangla": str, "english": str}, ...],
  "answer": {"bangla": str, "english": str},
  "session": str,
  "department": str,
  "qno": int
}
"""

from __future__ import annotations
import re
import json
from typing import Optional, List, Tuple, Dict
from pathlib import Path
try:
    from docx import Document
    _HAS_PYDOCX = True
except Exception:
    Document = None  # type: ignore
    _HAS_PYDOCX = False
from io import BytesIO
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..authentication import CustomJWTAuthentication
from drf_spectacular.utils import extend_schema, OpenApiResponse

# Optional; if unavailable, we no-op
try:
    from bijoy2unicode import bijoy2unicode  # type: ignore
except Exception:
    def bijoy2unicode(t: str) -> str:
        return t

BANG2ENG = {"ক": "A", "খ": "B", "গ": "C", "ঘ": "D"}
ENG2BANG = {v: k for k, v in BANG2ENG.items()}


def bengali_digits_to_english(s: str) -> str:
    return s.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))


def _clean(s: str) -> str:
    return re.sub(r"[ \t]+", " ", (s or "").strip())


def find_answer_table_map(doc: Document) -> Dict[int, str]:
    """Find a 2-row (numbers/answers) table and build q -> raw answer mapping."""
    for table in doc.tables:
        if len(table.rows) < 2:
            continue
        r1 = " ".join(c.text.strip() for c in table.rows[0].cells if c.text.strip())
        r2 = " ".join(c.text.strip() for c in table.rows[1].cells if c.text.strip())

        nums = re.findall(r"\d+|[০-৯]+", r1)
        ans = re.findall(r"[কখগঘA-Da-d]|\([কখগঘ]\)|\([A-Da-d]\)", r2)

        if len(nums) >= 2 and len(nums) == len(ans):
            out: Dict[int, str] = {}
            for n, a in zip(nums, ans):
                n = bengali_digits_to_english(n)
                try:
                    qnum = int(re.sub(r"\D", "", n))
                except Exception:
                    continue
                out[qnum] = a.strip()
            if out:
                return out
    return {}


def fallback_answers_from_text(after_answer_text: str) -> Dict[int, str]:
    """
    If no answer table, read vertical lines after 'Answer:' — collect all numbers then all letters.
    Works with Physics paper style.
    """
    lines = [ln.strip() for ln in (after_answer_text or "").splitlines() if ln.strip()]
    if not lines:
        return {}
    all_nums, all_ans = [], []
    for ln in lines:
        all_nums += re.findall(r"\d+|[০-৯]+", ln)
    for ln in lines:
        all_ans += re.findall(r"[কখগঘA-Da-d]|\([কখগঘ]\)|\([A-Da-d]\)", ln)

    if all_nums and len(all_nums) == len(all_ans):
        out: Dict[int, str] = {}
        for n, a in zip(all_nums, all_ans):
            n = bengali_digits_to_english(n)
            try:
                qnum = int(re.sub(r"\D", "", n))
            except Exception:
                continue
            out[qnum] = a.strip()
        return out
    return {}


def normalize_answer_cell(raw: str) -> Tuple[str, str]:
    """Return tuple (bangla '(খ)' or '', english '(B)' or '')."""
    if not raw:
        return ("", "")
    raw = raw.strip()
    m_b = re.search(r"[কখগঘ]", raw)
    if m_b:
        b = m_b.group()
        e = BANG2ENG.get(b, "")
        return (f"({b})", f"({e})" if e else "")
    m_e = re.search(r"[A-Da-d]", raw)
    if m_e:
        e = m_e.group().upper()
        b = ENG2BANG.get(e, "")
        return (f"({b})" if b else "", f"({e})")
    # loose first-char fallback
    ch = raw[:1]
    if ch in BANG2ENG:
        return (f"({ch})", f"({BANG2ENG[ch]})")
    chU = ch.upper()
    if chU in ENG2BANG:
        return (f"({ENG2BANG[chU]})", f"({chU})")
    return ("", "")


def extract_questions_from_text(before_answer_text: str) -> List[Tuple[Optional[int], str]]:
    """
    Split on Bangla or English-numbered questions:
    - Bangla: '১। ...'
    - English: '1.' or '1)'
    """
    txt = (before_answer_text or "").strip()
    if not txt:
        return []
    # Guard header text: split only when a line starts with number-like prefix
    blocks = re.split(r"(?m)(?=^(?:\d+|[০-৯]+)[\.\।\)])", txt)
    result: List[Tuple[Optional[int], str]] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = re.match(r"^(?P<num>\d+|[০-৯]+)[\.\।\)]\s*(?P<body>.*)$", block, flags=re.S)
        if not m:
            # skip header or garbage
            continue
        num = m.group("num")
        try:
            num_int: Optional[int] = int(bengali_digits_to_english(num))
        except Exception:
            num_int = None
        body = (m.group("body") or "").strip()
        result.append((num_int, body))
    return result


# STRICT option labels (fixes false matches like the 'ক' in 'কত?'):
# - Accept "(ক)" or bare token "ক)"/"ক."/"ক:" only at a token boundary.
_BN_LABEL = r"(?:\(([কখগঘ])\)|(?<!\S)([কখগঘ])[\)\.\-:])"
_EN_LABEL = r"(?:\(([A-Da-d])\)|(?<!\S)([A-Da-d])[\)\.\-:])"


def extract_options_from_block(block_text: str) -> Tuple[str, List[Dict[str, str]]]:
    """
    Bangla+English option extractor (Bangla labels drive; English text inferred).
    Works when options are labeled as (ক) or bare token ক)/ক./ক:
    """
    text = (block_text or "")
    first = re.search(_BN_LABEL, text)
    if not first:
        return _clean(text), []

    question_only = _clean(text[: first.start()])
    zone = text[first.start():]

    options: List[Dict[str, str]] = []
    matches = list(re.finditer(_BN_LABEL, zone))
    for idx, m in enumerate(matches):
        # label may be in group(1) when "(ক)" form, or group(2) when bare "ক)" form
        letter = m.group(1) or m.group(2)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(zone)
        content = _clean(zone[start:end])
        if not content:
            continue

        eng_label = BANG2ENG.get(letter, chr(ord("A") + idx))
        # If English text appears inside parentheses within content, pick it as translation; else strip Bangla letters
        eng_in = re.search(r"\(([^()]*[A-Za-z0-9].*?)\)", content)
        eng_val = eng_in.group(1).strip() if eng_in else re.sub(r"[\u0980-\u09FF]+", " ", content).strip()

        options.append({
            "bangla": f"({letter}) {bijoy2unicode(content)}".strip(),
            "english": f"({eng_label}) {eng_val}".strip()
        })
    return question_only, options


def split_bangla_english_question(text: str) -> Tuple[str, str]:
    """
    For BN+EN combined stems like: '... ? (If ... then ...)'
    Returns (bangla_part, english_parenthetical_or_empty)
    """
    text = (text or "").strip()
    m = re.search(r"\(([^()]*[A-Za-z0-9].*?)\)", text)
    if m:
        eng = m.group(1).strip()
        bangla = (text[: m.start()] + text[m.end():]).strip()
        return bijoy2unicode(bangla), eng
    return bijoy2unicode(text), ""


def _extract_meta(doc: Document, all_text: str, file_path: str) -> Tuple[str, str, str]:
    # Subject
    sub_m = re.search(r"Sub(?:ject)?\s*[:\-]\s*([^\n\[]+)", all_text or "", flags=re.IGNORECASE)
    subject = re.sub(r"\[.*?\]", "", sub_m.group(1)).strip() if sub_m else "Unknown"
    # Session
    ses_m = re.search(r"(Spring|Fall|Summer)\s*[- ]?\s*(\d{4})", all_text or "", flags=re.IGNORECASE)
    session = f"{ses_m.group(1).capitalize()} {ses_m.group(2)}" if ses_m else ""
    # Department (paragraphs, then tables, then filename fallback like ...-CSE.docx)
    dept = None
    for p in doc.paragraphs[:30]:
        dm = re.search(r"Department\s*:?(\s*[A-Za-z]+)?", p.text, flags=re.IGNORECASE)
        if dm:
            cand = (dm.group(1) or "").strip().strip(":").strip()
            if cand:
                dept = cand
                break
    if not dept:
        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    if "Department" in cell.text:
                        after = cell.text.split("Department", 1)[1]
                        m = re.search(r":\s*([A-Za-z]+)", after)
                        if m:
                            dept = m.group(1)
                            break
                if dept:
                    break
            if dept:
                break
    if not dept:
        m = re.search(r"-\s*([A-Za-z]{2,4})\.\w+$", file_path or "")
        if m:
            dept = m.group(1)
    if not dept:
        dept = "CSE"
    return bijoy2unicode(subject), session, bijoy2unicode(dept)


def parse_docx_file(path: str, output_json: Optional[str] = None):
    if not _HAS_PYDOCX:
        raise RuntimeError("python-docx is not installed; cannot parse .docx files")

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    doc = Document(str(p))
    paras = [pp.text.rstrip() for pp in doc.paragraphs]
    all_text = "\n".join(paras)  # real newlines

    subject, session, dept = _extract_meta(doc, all_text, str(p))

    # Answers (table first, then fallback after "Answer:")
    answers_map = find_answer_table_map(doc)
    if not answers_map:
        parts = re.split(r"Answer\s*:", all_text, flags=re.IGNORECASE)
        after = parts[1] if len(parts) > 1 else ""
        answers_map = fallback_answers_from_text(after)

    # Questions (everything before "Answer:")
    before_answer_text = re.split(r"Answer\s*:", all_text, flags=re.IGNORECASE)[0]
    q_blocks = extract_questions_from_text(before_answer_text)

    output = []
    for (qnum, block_text) in q_blocks:
        q_text, options = extract_options_from_block(block_text)
        q_bangla, q_english = split_bangla_english_question(q_text)

        ans_raw = answers_map.get(qnum, "")
        ans_b, ans_e = normalize_answer_cell(ans_raw)

        item = {
            "subject": subject,
            "question_bangla": q_bangla,
            "question_english": q_english,
            "options": options,
            "answer": {"bangla": ans_b, "english": ans_e},
            "semester": session,
            "department": dept,
            "qno": qnum
        }
        output.append(item)

    if not output_json:
        output_json = str(p.with_suffix(".json"))
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return output


def parse_docx_fileobj(fileobj, filename: str):
    """Parse a file-like .docx (UploadedFile) and return the extracted list of items.

    This mirrors parse_docx_file but reads from an in-memory file instead of path.
    """
    # python-docx accepts a file-like object, ensure it's BytesIO
    if not _HAS_PYDOCX:
        raise RuntimeError("python-docx is not installed; cannot parse .docx files")

    data = fileobj.read()
    bio = BytesIO(data)
    doc = Document(bio)

    paras = [pp.text.rstrip() for pp in doc.paragraphs]
    all_text = "\n".join(paras)

    subject, session, dept = _extract_meta(doc, all_text, filename)

    # Answers (table first, then fallback after "Answer:")
    answers_map = find_answer_table_map(doc)
    if not answers_map:
        parts = re.split(r"Answer\s*:", all_text, flags=re.IGNORECASE)
        after = parts[1] if len(parts) > 1 else ""
        answers_map = fallback_answers_from_text(after)

    before_answer_text = re.split(r"Answer\s*:", all_text, flags=re.IGNORECASE)[0]
    q_blocks = extract_questions_from_text(before_answer_text)

    output = []
    for (qnum, block_text) in q_blocks:
        q_text, options = extract_options_from_block(block_text)
        q_bangla, q_english = split_bangla_english_question(q_text)

        ans_raw = answers_map.get(qnum, "")
        ans_b, ans_e = normalize_answer_cell(ans_raw)
        ans_b = re.sub(r"[()]", "", ans_b).strip()
        ans_e = re.sub(r"[()]", "", ans_e).strip()

        options_bangla = {}
        options_english = {}
        for opt in options:
            b_text = opt.get("bangla", "").strip()
            e_text = opt.get("english", "").strip()

            match_b = re.match(r"[\(（]?([ক-ঘ])[\)）]?\s*(.*)", b_text)
            match_e = re.match(r"[\(（]?([A-Da-d])[\)）]?\s*(.*)", e_text)

            if match_b:
                options_bangla[match_b.group(1)] = match_b.group(2).strip()
            if match_e:
                options_english[match_e.group(1).upper()] = match_e.group(2).strip()

        options_structured = {"both": options_bangla, "english": options_english}
        item = {
            "subject": subject,
            "question_bangla": q_bangla,
            "question_english": q_english,
            "question_both": f"{q_bangla}({q_english})".strip(),
            "options": options_structured,
            "answer": {
                "both": [ans_b] if ans_b else [],
                "english": [ans_e] if ans_e else []
            },
            "semester": session,
            "department": dept,
        }
        output.append(item)

    return output


@extend_schema(
    operation_id='upload_docx_scrape',
    tags=['Document Scraper'],
    summary='Upload one or many .docx files and extract questions',
    description='Accepts multipart/form-data with key "files" as one-or-many .docx files; returns extracted JSON per file.',
    responses={200: OpenApiResponse(description='Extraction results')}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def upload_docx_scrape(request):
    """Upload one-or-many .docx files and return parsed extraction results."""
    files = request.FILES.getlist('files')
    if not files:
        return Response({'success': False, 'message': 'No files provided. Use multipart/form-data with key "files".'}, status=status.HTTP_400_BAD_REQUEST)

    results = []
    for f in files:
        try:
            if not f.name.lower().endswith('.docx'):
                results.append({'filename': f.name, 'success': False, 'message': 'Unsupported file type'})
                continue
            extracted = parse_docx_fileobj(f, f.name)
            results.append({'filename': f.name, 'success': True, 'count': len(extracted), 'data': extracted})
        except Exception as e:
            results.append({'filename': f.name, 'success': False, 'message': str(e)})

    return Response({'success': True, 'results': results})


# ---------------- CLI ----------------

def _iter_docx_paths(p):
    p = Path(p)
    if p.is_dir():
        for f in sorted(p.glob("*.docx")):
            yield f
    elif p.is_file() and p.suffix.lower() == ".docx":
        yield p
    else:
        raise FileNotFoundError(f"No .docx found at {p}")


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Bangla+English Q/A scraper")
    ap.add_argument("path", nargs="?", help="Input .docx file or directory (interactive prompt if omitted)")
    ap.add_argument("-o", "--outdir", default=None, help="Output directory for .json (defaults beside input)")
    ap.add_argument("--summary", action="store_true", help="Print a compact summary per file")
    ap.add_argument("--stdout", action="store_true", help="Print JSON to stdout (single-file only)")
    args = ap.parse_args()

    if not args.path:
        try:
            args.path = input("Enter .docx file or directory path: ").strip()
        except EOFError:
            ap.error("No path provided.")

    paths = list(_iter_docx_paths(args.path))
    if not paths:
        ap.error("No .docx files found.")

    multiple = len(paths) > 1
    for docx in paths:
        out_json = None
        if args.outdir:
            Path(args.outdir).mkdir(parents=True, exist_ok=True)
            out_json = str(Path(args.outdir) / (docx.stem + ".json"))
        res = parse_docx_file(str(docx), out_json)

        if args.summary:
            q = len(res)
            miss_ans = sum(1 for x in res if not (x["answer"]["english"] or x["answer"]["bangla"]))
            zero_opt = sum(1 for x in res if not x["options"])
            print(f"{docx.name}: {q} questions, {zero_opt} with 0 options, {miss_ans} with empty answer")

        if args.stdout and not multiple:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            if not args.summary:
                print(f"✅ Parsed {len(res)} questions → {Path(out_json or Path(docx).with_suffix('.json'))}")


if __name__ == "__main__":
    _cli()
