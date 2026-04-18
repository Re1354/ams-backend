#!/usr/bin/env python3
"""Structure-aware Bangla+English admission Q/A scraper for `.docx` files."""

from __future__ import annotations

import argparse
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..authentication import CustomJWTAuthentication

try:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    _HAS_PYDOCX = True
except Exception:
    Document = None  # type: ignore
    Table = None  # type: ignore
    Paragraph = None  # type: ignore
    _HAS_PYDOCX = False

try:
    from bijoy2unicode import bijoy2unicode  # type: ignore
except Exception:
    def bijoy2unicode(text: str) -> str:
        return text


BANG2ENG = {"ক": "A", "খ": "B", "গ": "C", "ঘ": "D"}
ENG2BANG = {value: key for key, value in BANG2ENG.items()}
QUESTION_START_RE = re.compile(r"^(?P<num>\d+|[০-৯]+)[\.\।\)]\s*(?P<body>.*)$", re.S)
_BN_LABEL = r"(?:\(([কখগঘ])\)|(?<!\S)([কখগঘ])[\)\.\-:])"
_ANSWER_SPLIT_RE = re.compile(r"Answer\s*:", flags=re.IGNORECASE)


def bengali_digits_to_english(value: str) -> str:
    return value.translate(str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789"))


def _clean(value: str) -> str:
    return re.sub(r"[ \t]+", " ", (value or "").strip())


def _is_blankish(value: str) -> bool:
    normalized = _clean(value)
    return not normalized or normalized in {",", ".", ":", "-", "--"}


def _iter_document_blocks(doc: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            text = _clean(bijoy2unicode(block.text))
            if text:
                blocks.append({"type": "paragraph", "text": text})
            continue

        if isinstance(block, Table):
            rows: list[list[str]] = []
            for row in block.rows:
                cell_texts = [_clean(bijoy2unicode(cell.text)) for cell in row.cells]
                filtered = [text for text in cell_texts if text]
                if filtered:
                    rows.append(filtered)
            if rows:
                blocks.append({"type": "table", "rows": rows})

    return blocks


def _flatten_blocks_to_text(blocks: Iterable[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        if block["type"] == "paragraph":
            lines.append(block["text"])
        else:
            lines.extend(" ".join(row) for row in block["rows"])
    return "\n".join(lines)


def find_answer_table_map(blocks: Iterable[dict[str, Any]]) -> Dict[int, str]:
    """Find a 2-row (numbers/answers) table and build q -> raw answer mapping."""
    best_match: Dict[int, str] = {}

    for block in blocks:
        if block["type"] != "table":
            continue

        rows = block["rows"]
        if len(rows) < 2:
            continue

        header = " ".join(rows[0])
        answers = " ".join(rows[1])
        numbers = re.findall(r"\d+|[০-৯]+", header)
        labels = re.findall(r"[কখগঘA-Da-d]|\([কখগঘ]\)|\([A-Da-d]\)", answers)

        if numbers and len(numbers) == len(labels):
            parsed: Dict[int, str] = {}
            for number_text, label in zip(numbers, labels):
                try:
                    qno = int(re.sub(r"\D", "", bengali_digits_to_english(number_text)))
                except ValueError:
                    continue
                parsed[qno] = label.strip()

            if len(parsed) > len(best_match):
                best_match = parsed

    return best_match


def fallback_answers_from_text(lines: Iterable[str]) -> Dict[int, str]:
    """Fallback vertical answer parser from the lines after `Answer:`."""
    clean_lines = [_clean(line) for line in lines if _clean(line)]
    if not clean_lines:
        return {}

    all_numbers: list[str] = []
    all_answers: list[str] = []
    for line in clean_lines:
        all_numbers.extend(re.findall(r"\d+|[০-৯]+", line))
        all_answers.extend(re.findall(r"[কখগঘA-Da-d]|\([কখগঘ]\)|\([A-Da-d]\)", line))

    if not all_numbers or len(all_numbers) != len(all_answers):
        return {}

    parsed: Dict[int, str] = {}
    for number_text, answer_text in zip(all_numbers, all_answers):
        try:
            qno = int(re.sub(r"\D", "", bengali_digits_to_english(number_text)))
        except ValueError:
            continue
        parsed[qno] = answer_text.strip()
    return parsed


def normalize_answer_cell(raw: str) -> Tuple[str, str]:
    """Return tuple (bangla '(খ)' or '', english '(B)' or '')."""
    if not raw:
        return ("", "")

    raw = raw.strip()
    match_bangla = re.search(r"[কখগঘ]", raw)
    if match_bangla:
        bangla = match_bangla.group()
        english = BANG2ENG.get(bangla, "")
        return (f"({bangla})", f"({english})" if english else "")

    match_english = re.search(r"[A-Da-d]", raw)
    if match_english:
        english = match_english.group().upper()
        bangla = ENG2BANG.get(english, "")
        return (f"({bangla})" if bangla else "", f"({english})")

    first_char = raw[:1]
    if first_char in BANG2ENG:
        return (f"({first_char})", f"({BANG2ENG[first_char]})")

    first_upper = first_char.upper()
    if first_upper in ENG2BANG:
        return (f"({ENG2BANG[first_upper]})", f"({first_upper})")

    return ("", "")


def extract_question_blocks_from_lines(lines: Iterable[str]) -> List[Tuple[Optional[int], str]]:
    blocks: List[Tuple[Optional[int], str]] = []
    current_number: Optional[int] = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_number, current_lines
        if current_number is not None and current_lines:
            blocks.append((current_number, "\n".join(current_lines).strip()))
        current_number = None
        current_lines = []

    for raw_line in lines:
        line = _clean(raw_line)
        if not line:
            continue

        match = QUESTION_START_RE.match(line)
        if match:
            flush()
            try:
                current_number = int(bengali_digits_to_english(match.group("num")))
            except ValueError:
                current_number = None
            body = _clean(match.group("body"))
            if body:
                current_lines.append(body)
            continue

        if current_number is not None:
            current_lines.append(line)

    flush()
    return blocks


def extract_options_from_block(block_text: str) -> Tuple[str, List[Dict[str, str]]]:
    """Extract the question-only stem and option pairs from a question block."""
    text = _clean(block_text.replace("\n", " "))
    first = re.search(_BN_LABEL, text)
    if not first:
        return text, []

    question_only = _clean(text[: first.start()])
    option_zone = text[first.start() :]
    options: List[Dict[str, str]] = []
    matches = list(re.finditer(_BN_LABEL, option_zone))

    for index, match in enumerate(matches):
        letter = match.group(1) or match.group(2)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(option_zone)
        content = _clean(option_zone[start:end])
        if not content:
            continue

        english_label = BANG2ENG.get(letter, chr(ord("A") + index))
        english_inline = re.search(r"\(([^()]*[A-Za-z0-9].*?)\)", content)
        english_text = (
            english_inline.group(1).strip()
            if english_inline
            else re.sub(r"[\u0980-\u09FF]+", " ", content).strip()
        )

        options.append(
            {
                "bangla": f"({letter}) {bijoy2unicode(content)}".strip(),
                "english": f"({english_label}) {english_text}".strip(),
            }
        )

    return question_only, options


def split_bangla_english_question(text: str) -> Tuple[str, str]:
    """Split a combined Bangla+English stem into separate strings."""
    text = _clean(text)
    match = re.search(r"\(([^()]*[A-Za-z0-9].*?)\)", text)
    if match:
        english = match.group(1).strip()
        bangla = _clean(text[: match.start()] + text[match.end() :])
        return bijoy2unicode(bangla), english
    return bijoy2unicode(text), ""


def _extract_meta(doc: Any, blocks: list[dict[str, Any]], file_path: str) -> Tuple[str, str, str]:
    full_text = _flatten_blocks_to_text(blocks)

    subject_match = re.search(r"Sub(?:ject)?\s*[:\-]\s*([^\n\[]+)", full_text, flags=re.IGNORECASE)
    subject = (
        re.sub(r"\[.*?\]", "", subject_match.group(1)).strip()
        if subject_match
        else "Unknown"
    )

    session_match = re.search(r"(Spring|Fall|Summer)\s*[- ]?\s*(\d{4})", full_text, flags=re.IGNORECASE)
    session = f"{session_match.group(1).capitalize()} {session_match.group(2)}" if session_match else ""

    department = ""
    for block in blocks[:30]:
        if block["type"] == "paragraph":
            match = re.search(r"Department\s*:?\s*([A-Za-z]+)", block["text"], flags=re.IGNORECASE)
            if match:
                department = match.group(1)
                break
        else:
            for row in block["rows"]:
                joined = " ".join(row)
                match = re.search(r"Department\s*:?\s*([A-Za-z]+)", joined, flags=re.IGNORECASE)
                if match:
                    department = match.group(1)
                    break
            if department:
                break

    if not department:
        filename_match = re.search(r"-\s*([A-Za-z]{2,4})\.\w+$", file_path or "")
        department = filename_match.group(1) if filename_match else "CSE"

    return bijoy2unicode(subject), session, bijoy2unicode(department)


def _split_question_and_answer_regions(blocks: list[dict[str, Any]]) -> Tuple[list[str], list[str]]:
    question_lines: list[str] = []
    answer_lines: list[str] = []
    in_answer_section = False

    for block in blocks:
        if block["type"] == "paragraph":
            text = block["text"]
            if not in_answer_section and _ANSWER_SPLIT_RE.search(text):
                parts = _ANSWER_SPLIT_RE.split(text, maxsplit=1)
                before = parts[0] if parts else ""
                after = parts[1] if len(parts) > 1 else ""
                if _clean(before):
                    question_lines.append(_clean(before))
                if _clean(after):
                    answer_lines.append(_clean(after))
                in_answer_section = True
                continue

            if in_answer_section:
                answer_lines.append(text)
            else:
                question_lines.append(text)
            continue

        target = answer_lines if in_answer_section else question_lines
        target.extend(" ".join(row) for row in block["rows"])

    return question_lines, answer_lines


def _structure_options(options: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    options_bangla: Dict[str, str] = {}
    options_english: Dict[str, str] = {}

    for option in options:
        bangla_text = option.get("bangla", "").strip()
        english_text = option.get("english", "").strip()

        match_bangla = re.match(r"[\(（]?([ক-ঘ])[\)）]?\s*(.*)", bangla_text)
        match_english = re.match(r"[\(（]?([A-Da-d])[\)）]?\s*(.*)", english_text)

        if match_bangla:
            options_bangla[match_bangla.group(1)] = match_bangla.group(2).strip()
        if match_english:
            options_english[match_english.group(1).upper()] = match_english.group(2).strip()

    return {"both": options_bangla, "english": options_english}


def _parse_docx_document(doc: Any, filename: str) -> list[dict[str, Any]]:
    blocks = _iter_document_blocks(doc)
    subject, session, department = _extract_meta(doc, blocks, filename)
    question_lines, answer_lines = _split_question_and_answer_regions(blocks)

    answers_map = find_answer_table_map(blocks)
    if not answers_map:
        answers_map = fallback_answers_from_text(answer_lines)

    output = []
    for question_number, block_text in extract_question_blocks_from_lines(question_lines):
        question_text, options = extract_options_from_block(block_text)
        question_bangla, question_english = split_bangla_english_question(question_text)

        answer_raw = answers_map.get(question_number or -1, "")
        answer_bangla, answer_english = normalize_answer_cell(answer_raw)
        answer_bangla = re.sub(r"[()]", "", answer_bangla).strip()
        answer_english = re.sub(r"[()]", "", answer_english).strip()

        question_both = question_bangla
        if question_english:
            question_both = f"{question_bangla} ({question_english})".strip()

        output.append(
            {
                "subject": subject,
                "question_bangla": question_bangla,
                "question_english": question_english,
                "question_both": question_both,
                "options": _structure_options(options),
                "answer": {
                    "both": [answer_bangla] if answer_bangla else [],
                    "english": [answer_english] if answer_english else [],
                },
                "semester": session,
                "department": department,
                "qno": question_number,
            }
        )

    return output


def parse_docx_file(path: str, output_json: Optional[str] = None):
    if not _HAS_PYDOCX:
        raise RuntimeError("python-docx is not installed; cannot parse .docx files")

    docx_path = Path(path)
    if not docx_path.exists():
        raise FileNotFoundError(docx_path)

    output = _parse_docx_document(Document(str(docx_path)), str(docx_path))
    if not output_json:
        output_json = str(docx_path.with_suffix(".json"))

    with open(output_json, "w", encoding="utf-8") as output_file:
        json.dump(output, output_file, ensure_ascii=False, indent=2)

    return output


def parse_docx_fileobj(fileobj, filename: str):
    if not _HAS_PYDOCX:
        raise RuntimeError("python-docx is not installed; cannot parse .docx files")

    data = fileobj.read()
    return _parse_docx_document(Document(BytesIO(data)), filename)


@extend_schema(
    operation_id="upload_docx_scrape",
    tags=["Document Scraper"],
    summary="Upload one or many .docx files and extract questions",
    description='Accepts multipart/form-data with key "files" as one-or-many .docx files; returns extracted JSON per file.',
    responses={200: OpenApiResponse(description="Extraction results")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def upload_docx_scrape(request):
    files = request.FILES.getlist("files")
    if not files:
        return Response(
            {"success": False, "message": 'No files provided. Use multipart/form-data with key "files".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    results = []
    for uploaded_file in files:
        try:
            if not uploaded_file.name.lower().endswith(".docx"):
                results.append(
                    {
                        "filename": uploaded_file.name,
                        "success": False,
                        "message": "Unsupported file type",
                    }
                )
                continue

            extracted = parse_docx_fileobj(uploaded_file, uploaded_file.name)
            results.append(
                {
                    "filename": uploaded_file.name,
                    "success": True,
                    "count": len(extracted),
                    "data": extracted,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "filename": uploaded_file.name,
                    "success": False,
                    "message": str(exc),
                }
            )

    return Response({"success": True, "results": results})


def _iter_docx_paths(path_value: str):
    path = Path(path_value)
    if path.is_dir():
        for file_path in sorted(path.glob("*.docx")):
            yield file_path
    elif path.is_file() and path.suffix.lower() == ".docx":
        yield path
    else:
        raise FileNotFoundError(f"No .docx found at {path}")


def _cli():
    parser = argparse.ArgumentParser(description="Bangla+English Q/A scraper")
    parser.add_argument("path", nargs="?", help="Input .docx file or directory")
    parser.add_argument("-o", "--outdir", default=None, help="Output directory for .json")
    parser.add_argument("--summary", action="store_true", help="Print a compact summary per file")
    parser.add_argument("--stdout", action="store_true", help="Print JSON to stdout (single-file only)")
    args = parser.parse_args()

    if not args.path:
        try:
            args.path = input("Enter .docx file or directory path: ").strip()
        except EOFError:
            parser.error("No path provided.")

    docx_paths = list(_iter_docx_paths(args.path))
    if not docx_paths:
        parser.error("No .docx files found.")

    multiple = len(docx_paths) > 1
    for docx_path in docx_paths:
        output_json = None
        if args.outdir:
            Path(args.outdir).mkdir(parents=True, exist_ok=True)
            output_json = str(Path(args.outdir) / f"{docx_path.stem}.json")

        result = parse_docx_file(str(docx_path), output_json)

        if args.summary:
            zero_options = sum(
                1
                for item in result
                if not item["options"].get("both") and not item["options"].get("english")
            )
            missing_answers = sum(
                1
                for item in result
                if not (item["answer"]["both"] or item["answer"]["english"])
            )
            print(
                f"{docx_path.name}: {len(result)} questions, "
                f"{zero_options} with 0 options, {missing_answers} with empty answer"
            )
            continue

        if args.stdout and not multiple:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"✅ Parsed {len(result)} questions → {Path(output_json or docx_path.with_suffix('.json'))}")


if __name__ == "__main__":
    _cli()
