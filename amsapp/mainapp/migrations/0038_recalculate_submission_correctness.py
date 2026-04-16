import json

from django.db import migrations


def _normalize_token(value):
    return " ".join(str(value or "").split()).casefold()


def _parse_serialized_value(value):
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


def _collect_scalar_tokens(value):
    tokens = []

    def collect(item):
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


def _build_option_lookup(options):
    parsed_options = _parse_serialized_value(options)
    lookup = {}

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


def _extract_correct_option_answers(question):
    lookup = _build_option_lookup(question.options)
    candidates = _collect_scalar_tokens(question.answer)
    resolved_answers = []
    seen = set()

    for candidate in candidates:
        resolved = lookup.get(candidate, candidate)
        if resolved and resolved not in seen:
            seen.add(resolved)
            resolved_answers.append(resolved)

    return resolved_answers


def _is_submission_correct(question, submitted_answer):
    if question.type == "option":
        normalized_submitted = _normalize_token(submitted_answer)
        if not normalized_submitted:
            return False

        lookup = _build_option_lookup(question.options)
        resolved_submitted = lookup.get(normalized_submitted, normalized_submitted)
        return resolved_submitted in _extract_correct_option_answers(question)

    return _normalize_token(submitted_answer) == _normalize_token(question.answer)


def recalculate_submission_correctness(apps, schema_editor):
    Submission = apps.get_model("mainapp", "Submission")

    updated_submissions = []
    for submission in Submission.objects.select_related("question").all().iterator():
        expected = _is_submission_correct(submission.question, submission.answer)
        if submission.is_correct != expected:
            submission.is_correct = expected
            updated_submissions.append(submission)

    if updated_submissions:
        Submission.objects.bulk_update(updated_submissions, ["is_correct"])


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0037_canonicalize_semester_format"),
    ]

    operations = [
        migrations.RunPython(
            recalculate_submission_correctness,
            migrations.RunPython.noop,
        ),
    ]
