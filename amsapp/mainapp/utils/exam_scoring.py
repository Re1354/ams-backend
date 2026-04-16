import json
from collections import defaultdict
from typing import Any

from django.db.models import Sum


def _normalize_token(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def normalize_text_answer(value: Any) -> str:
    return _normalize_token(value)


def _parse_serialized_value(value: Any) -> Any:
    if value is None or isinstance(value, (list, dict)):
        return value

    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return ""

    try:
        return json.loads(stripped)
    except (TypeError, ValueError, json.JSONDecodeError):
        return stripped


def _collect_scalar_tokens(value: Any) -> list[str]:
    tokens: list[str] = []

    def collect(item: Any) -> None:
        parsed_item = _parse_serialized_value(item)

        if parsed_item is None:
            return

        if isinstance(parsed_item, list):
            for child in parsed_item:
                collect(child)
            return

        if isinstance(parsed_item, dict):
            preferred_keys = (
                "english",
                "both",
                "answer",
                "answers",
                "correct",
                "correct_answer",
                "correct_answers",
                "value",
                "values",
                "option",
                "options",
            )
            handled = False

            for key in preferred_keys:
                if key in parsed_item:
                    handled = True
                    collect(parsed_item[key])

            if not handled:
                for child in parsed_item.values():
                    collect(child)
            return

        normalized = _normalize_token(parsed_item)
        if normalized:
            tokens.append(normalized)

    collect(value)
    return tokens


def _build_option_lookup(options: Any) -> dict[str, str]:
    parsed_options = _parse_serialized_value(options)
    lookup: dict[str, str] = {}

    if not isinstance(parsed_options, dict):
        return lookup

    for option_key, option_value in parsed_options.items():
        normalized_key = _normalize_token(option_key)
        if normalized_key:
            lookup[normalized_key] = normalized_key

        normalized_value = _normalize_token(option_value)
        if normalized_value and normalized_value not in lookup:
            lookup[normalized_value] = normalized_key

    return lookup


def extract_correct_option_answers(question: Any) -> list[str]:
    lookup = _build_option_lookup(getattr(question, "options", None))
    candidates = _collect_scalar_tokens(getattr(question, "answer", None))
    normalized_answers: list[str] = []
    seen: set[str] = set()

    for candidate in candidates:
        resolved = lookup.get(candidate, candidate)
        if resolved and resolved not in seen:
            seen.add(resolved)
            normalized_answers.append(resolved)

    return normalized_answers


def is_submission_correct(question: Any, submitted_answer: Any) -> bool:
    if getattr(question, "type", "") == "option":
        normalized_submitted = _normalize_token(submitted_answer)
        if not normalized_submitted:
            return False

        lookup = _build_option_lookup(getattr(question, "options", None))
        resolved_submitted = lookup.get(normalized_submitted, normalized_submitted)
        return resolved_submitted in extract_correct_option_answers(question)

    return normalize_text_answer(submitted_answer) == normalize_text_answer(
        getattr(question, "answer", "")
    )


def calculate_grade(score_percentage: float) -> str:
    if score_percentage >= 90:
        return "A+"
    if score_percentage >= 80:
        return "A"
    if score_percentage >= 70:
        return "B"
    if score_percentage >= 60:
        return "C"
    if score_percentage >= 50:
        return "D"
    return "F"


def calculate_submission_summary(exam: Any, submissions: Any) -> dict[str, Any]:
    submission_list = list(submissions)
    total_attempted = len(submission_list)
    correct_answers = sum(1 for submission in submission_list if submission.is_correct)
    wrong_answers = total_attempted - correct_answers

    total_marks = exam.exam_questions.aggregate(total=Sum("marks"))["total"] or 0
    obtained_marks = sum(
        getattr(submission.question, "marks", 0)
        for submission in submission_list
        if submission.is_correct
    )
    score_percentage = round((obtained_marks / total_marks) * 100, 2) if total_marks > 0 else 0

    return {
        "total_questions_attempted": total_attempted,
        "correct_answers": correct_answers,
        "wrong_answers": wrong_answers,
        "obtained_marks": obtained_marks,
        "total_marks": total_marks,
        "score_percentage": score_percentage,
        "grade": calculate_grade(score_percentage),
    }


def build_subject_result_rows(exam: Any, submissions: Any) -> list[dict[str, Any]]:
    questions = list(
        exam.exam_questions.values("id", "subject", "marks")
    )
    submissions_by_question = {submission.question_id: submission for submission in submissions}
    subject_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "subject_id": "",
            "subject_name": "",
            "total_questions": 0,
            "correct_answers": 0,
            "wrong_answers": 0,
            "_total_marks": 0,
            "_obtained_marks": 0,
        }
    )

    for question in questions:
        subject_name = question["subject"]
        row = subject_data[subject_name]
        row["subject_id"] = subject_name
        row["subject_name"] = subject_name
        row["total_questions"] += 1
        row["_total_marks"] += question["marks"] or 0

        submission = submissions_by_question.get(question["id"])
        if not submission:
            continue

        if submission.is_correct:
            row["correct_answers"] += 1
            row["_obtained_marks"] += question["marks"] or 0
        else:
            row["wrong_answers"] += 1

    rows: list[dict[str, Any]] = []
    for row in subject_data.values():
        total_marks = row.pop("_total_marks")
        obtained_marks = row.pop("_obtained_marks")
        row["score_percentage"] = (
            round((obtained_marks / total_marks) * 100, 2) if total_marks > 0 else 0
        )
        rows.append(row)

    rows.sort(key=lambda item: item["subject_name"])
    return rows
