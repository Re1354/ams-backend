import re

from django.db import migrations


TERM_LOOKUP = {
    "spring": "Spring",
    "summer": "Summer",
    "fall": "Fall",
}
SEMESTER_PATTERN = re.compile(r"^(spring|summer|fall)[\s-]+(\d{4})$", re.IGNORECASE)


def normalize_semester(value, allow_blank=False):
    if value is None:
        return "" if allow_blank else None

    text = str(value).strip()
    if not text:
        return "" if allow_blank else None

    compact = re.sub(r"\s+", " ", text.replace("-", " ")).strip()
    match = SEMESTER_PATTERN.fullmatch(compact)
    if not match:
        return text

    return f"{TERM_LOOKUP[match.group(1).lower()]} {match.group(2)}"


def normalize_semester_list(values):
    normalized = []
    seen = set()

    for value in values or []:
        canonical = normalize_semester(value)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)

    return normalized


def forwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    Exam = apps.get_model("mainapp", "Exam")
    Students = apps.get_model("mainapp", "Students")
    ScrappedQuestion = apps.get_model("mainapp", "ScrappedQuestion")
    BlocklistQuestion = apps.get_model("mainapp", "BlocklistQuestion")
    ExamQuestion = apps.get_model("mainapp", "ExamQuestion")
    AdmissionConfiguration = apps.get_model("mainapp", "AdmissionConfiguration")
    AdmissionResult = apps.get_model("mainapp", "AdmissionResult")

    grouped_configurations = {}
    for configuration in AdmissionConfiguration.objects.using(db_alias).order_by("id"):
        canonical = normalize_semester(configuration.semester)
        key = (configuration.department_id, canonical)
        grouped_configurations.setdefault(key, []).append(configuration)

    for (department_id, canonical), configurations in grouped_configurations.items():
        primary = next(
            (item for item in configurations if item.semester == canonical),
            configurations[0],
        )

        for duplicate in configurations:
            if duplicate.id == primary.id:
                continue

            AdmissionResult.objects.using(db_alias).filter(
                configuration_id=duplicate.id
            ).update(configuration_id=primary.id)

            update_fields = []
            if not primary.exam_id and duplicate.exam_id:
                primary.exam_id = duplicate.exam_id
                update_fields.append("exam")
            if primary.seat_limit <= 0 and duplicate.seat_limit > 0:
                primary.seat_limit = duplicate.seat_limit
                update_fields.append("seat_limit")
            if primary.threshold <= 0 and duplicate.threshold > 0:
                primary.threshold = duplicate.threshold
                update_fields.append("threshold")
            if not (primary.notes or "").strip() and (duplicate.notes or "").strip():
                primary.notes = duplicate.notes
                update_fields.append("notes")

            if update_fields:
                primary.save(update_fields=update_fields, using=db_alias)

            duplicate.delete(using=db_alias)

        if primary.semester != canonical:
            primary.semester = canonical
            primary.save(update_fields=["semester"], using=db_alias)

    for exam in Exam.objects.using(db_alias).all():
        canonical_semester = normalize_semester(exam.semester)
        canonical_except = normalize_semester_list(exam.except_semesters)
        update_fields = []

        if canonical_semester != exam.semester:
            exam.semester = canonical_semester
            update_fields.append("semester")

        if canonical_except != (exam.except_semesters or []):
            exam.except_semesters = canonical_except
            update_fields.append("except_semesters")

        if update_fields:
            exam.save(update_fields=update_fields, using=db_alias)

    for student in Students.objects.using(db_alias).all():
        canonical = normalize_semester(student.registration_semester)
        if canonical != student.registration_semester:
            student.registration_semester = canonical
            student.save(update_fields=["registration_semester"], using=db_alias)

    for question in ScrappedQuestion.objects.using(db_alias).all():
        canonical = normalize_semester(question.semester)
        if canonical != question.semester:
            question.semester = canonical
            question.save(update_fields=["semester"], using=db_alias)

    for question in BlocklistQuestion.objects.using(db_alias).all():
        canonical = normalize_semester(question.semester)
        if canonical != question.semester:
            question.semester = canonical
            question.save(update_fields=["semester"], using=db_alias)

    for question in ExamQuestion.objects.using(db_alias).all():
        canonical = normalize_semester(question.semester, allow_blank=True)
        if canonical != question.semester:
            question.semester = canonical
            question.save(update_fields=["semester"], using=db_alias)


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0036_alter_admissionresult_options_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
