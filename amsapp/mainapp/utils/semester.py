import re


TERM_ORDER = {"Spring": 1, "Summer": 2, "Fall": 3}
TERM_LOOKUP = {term.lower(): term for term in TERM_ORDER}
SEMESTER_PATTERN = re.compile(r"^(spring|summer|fall)[\s-]+(\d{4})$", re.IGNORECASE)


def normalize_semester_value(value, allow_blank=False):
    if value is None:
        if allow_blank:
            return ""
        raise ValueError("Semester is required.")

    text = str(value).strip()
    if not text:
        if allow_blank:
            return ""
        raise ValueError("Semester is required.")

    compact = re.sub(r"\s+", " ", text.replace("-", " ")).strip()
    match = SEMESTER_PATTERN.fullmatch(compact)
    if not match:
        raise ValueError(
            "Semester must be in the format 'Spring 2026', 'Summer 2026', or 'Fall 2026'."
        )

    term = TERM_LOOKUP[match.group(1).lower()]
    year = match.group(2)
    return f"{term} {year}"


def normalize_semester_list(values):
    normalized = []
    seen = set()

    for value in values or []:
        canonical = normalize_semester_value(value)
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)

    return normalized


def normalize_semester_filter(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    try:
        return normalize_semester_value(text)
    except ValueError:
        return text


def semester_sort_key(value):
    try:
        canonical = normalize_semester_value(value)
    except ValueError:
        return (9999, 9999, str(value))

    term, year = canonical.rsplit(" ", 1)
    return (int(year), TERM_ORDER.get(term, 9999), canonical)
