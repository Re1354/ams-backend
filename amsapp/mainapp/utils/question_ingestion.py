from __future__ import annotations

from typing import Any

from django.db import transaction

from ..models import ScrappedQuestion
from .semester import normalize_semester_value

BANG_OPTION_KEYS = {"ক", "খ", "গ", "ঘ"}
ENG_OPTION_KEYS = {"A", "B", "C", "D"}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_blankish(value: Any) -> bool:
    normalized = _clean_text(value)
    return not normalized or normalized in {",", ".", ":", "-", "--"}


def _clean_option_map(option_map: Any, expected_keys: set[str]) -> dict[str, str]:
    if not isinstance(option_map, dict):
        return {}

    cleaned: dict[str, str] = {}
    for key, value in option_map.items():
        clean_key = _clean_text(key).upper() if expected_keys is ENG_OPTION_KEYS else _clean_text(key)
        clean_value = _clean_text(value)
        if clean_key in expected_keys and not _is_blankish(clean_value):
            cleaned[clean_key] = clean_value
    return cleaned


def _normalize_question_payload(item: dict[str, Any]) -> dict[str, Any]:
    question_bangla = _clean_text(item.get("question_bangla"))
    question_english = _clean_text(item.get("question_english"))
    question_both = _clean_text(item.get("question_both"))

    if not question_both:
        question_both = question_bangla
        if question_english:
            question_both = f"{question_bangla} ({question_english})".strip()

    options = item.get("options") if isinstance(item.get("options"), dict) else {}
    answers = item.get("answer") if isinstance(item.get("answer"), dict) else {}

    cleaned_both_options = _clean_option_map(options.get("both"), BANG_OPTION_KEYS)
    cleaned_english_options = _clean_option_map(options.get("english"), ENG_OPTION_KEYS)

    normalized = {
        "subject": _clean_text(item.get("subject")),
        "question_bangla": question_bangla,
        "question_english": question_english,
        "question_both": question_both,
        "options": {
            "both": cleaned_both_options,
            "english": cleaned_english_options,
        },
        "answer": {
            "both": [
                _clean_text(answer)
                for answer in (answers.get("both") or [])
                if _clean_text(answer)
            ],
            "english": [
                _clean_text(answer).upper()
                for answer in (answers.get("english") or [])
                if _clean_text(answer)
            ],
        },
        "marks": int(item.get("marks") or 1),
        "semester": normalize_semester_value(item.get("semester") or ""),
        "department_shortname": _clean_text(
            item.get("department_shortname") or item.get("department") or "CSE"
        ),
        "qno": item.get("qno"),
    }

    normalized["type"] = (
        "option"
        if normalized["options"]["both"] or normalized["options"]["english"]
        else "text"
    )
    return normalized


def validate_scraped_question_item(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = _normalize_question_payload(item)
    issues: list[str] = []

    if not normalized["subject"]:
        issues.append("Subject is missing.")

    if not normalized["question_both"] and not normalized["question_bangla"] and not normalized["question_english"]:
        issues.append("Question text is missing.")

    if normalized["type"] == "option":
        both_options = normalized["options"]["both"]
        english_options = normalized["options"]["english"]

        if both_options and len(both_options) != 4:
            issues.append("Bangla option set must contain 4 real options.")
        if english_options and len(english_options) != 4:
            issues.append("English option set must contain 4 real options.")
        if not both_options and not english_options:
            issues.append("Option question is missing real options.")

        both_answers = normalized["answer"]["both"]
        english_answers = normalized["answer"]["english"]

        if both_options:
            if len(both_answers) != 1 or both_answers[0] not in both_options:
                issues.append("Bangla answer key does not map to a real option.")
        if english_options:
            if len(english_answers) != 1 or english_answers[0] not in english_options:
                issues.append("English answer key does not map to a real option.")
        if not both_answers and not english_answers:
            issues.append("Option question is missing an answer key.")

    return normalized, issues


def _identity_tokens(question_payload: dict[str, Any]) -> set[str]:
    return {
        token
        for token in (
            _normalize_text(question_payload.get("question_bangla")),
            _normalize_text(question_payload.get("question_english")),
            _normalize_text(question_payload.get("question_both")),
        )
        if token
    }


def is_duplicate_scrapped_question(question_payload: dict[str, Any]) -> bool:
    tokens = _identity_tokens(question_payload)
    if not tokens:
        return False

    queryset = ScrappedQuestion.objects.filter(subject__iexact=question_payload["subject"])
    if question_payload["semester"]:
        queryset = queryset.filter(semester=question_payload["semester"])
    if question_payload["department_shortname"]:
        queryset = queryset.filter(
            department_shortname__iexact=question_payload["department_shortname"]
        )

    for existing in queryset.only("questions"):
        existing_questions = existing.questions if isinstance(existing.questions, dict) else {}
        existing_tokens = {
            token
            for token in (
                _normalize_text(existing_questions.get("bangla")),
                _normalize_text(existing_questions.get("english")),
                _normalize_text(existing_questions.get("both")),
            )
            if token
        }
        if tokens & existing_tokens:
            return True

    return False


def ingest_scraped_question_entries(entries: list[Any]) -> dict[str, Any]:
    created: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    file_summaries: list[dict[str, Any]] = []
    skipped_duplicates = 0

    with transaction.atomic():
        for file_entry in entries:
            data_list = file_entry.get("data") if isinstance(file_entry, dict) else None
            if not data_list and isinstance(file_entry, list):
                data_list = file_entry
            if not data_list:
                continue

            filename = file_entry.get("filename") if isinstance(file_entry, dict) else ""
            file_created = 0
            file_skipped = 0
            file_invalid = 0

            for item in data_list:
                normalized, issues = validate_scraped_question_item(item)
                if issues:
                    file_invalid += 1
                    invalid.append(
                        {
                            "filename": filename,
                            "question_no": normalized.get("qno"),
                            "subject": normalized["subject"],
                            "question_both": normalized["question_both"],
                            "issues": issues,
                        }
                    )
                    continue

                if is_duplicate_scrapped_question(normalized):
                    skipped_duplicates += 1
                    file_skipped += 1
                    continue

                question = ScrappedQuestion.objects.create(
                    subject=normalized["subject"],
                    questions={
                        "bangla": normalized["question_bangla"],
                        "english": normalized["question_english"],
                        "both": normalized["question_both"],
                    },
                    type=normalized["type"],
                    text=None,
                    options=normalized["options"],
                    answer=normalized["answer"],
                    marks=normalized["marks"],
                    semester=normalized["semester"],
                    department_shortname=normalized["department_shortname"] or "CSE",
                )
                created.append(
                    {
                        "id": question.id,
                        "subject": question.subject,
                        "question": normalized["question_both"],
                    }
                )
                file_created += 1

            file_summaries.append(
                {
                    "filename": filename,
                    "created_count": file_created,
                    "skipped_duplicates": file_skipped,
                    "invalid_count": file_invalid,
                }
            )

    return {
        "created_count": len(created),
        "skipped_duplicates": skipped_duplicates,
        "invalid_count": len(invalid),
        "created": created,
        "invalid": invalid,
        "files": file_summaries,
    }
