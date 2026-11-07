from django.db import migrations, models


def normalize_choices(raw_choices):
    normalized = []
    seen = set()
    if not isinstance(raw_choices, list):
        return normalized
    for position, choice in enumerate(raw_choices, start=1):
        if not isinstance(choice, dict):
            continue
        try:
            department_id = int(choice.get("department_id"))
            priority = int(choice.get("priority", position))
        except (TypeError, ValueError):
            continue
        if department_id <= 0 or department_id in seen:
            continue
        seen.add(department_id)
        normalized.append({"department_id": department_id, "priority": priority})
    normalized.sort(key=lambda choice: (choice["priority"], choice["department_id"]))
    return normalized


def backfill_choice_snapshots(apps, schema_editor):
    AdmissionResult = apps.get_model("mainapp", "AdmissionResult")
    Department = apps.get_model("mainapp", "Department")

    department_lookup = {}
    for department in Department.objects.all().only(
        "id", "department_name", "department_shortname"
    ):
        department_lookup[department.department_name.strip().casefold()] = department.id
        department_lookup[department.department_shortname.strip().casefold()] = department.id

    pending_updates = []
    queryset = AdmissionResult.objects.select_related("exam", "student", "department")
    for result in queryset.iterator(chunk_size=500):
        exam = result.exam
        label = (exam.department or "").strip()
        stored_type = (getattr(exam, "exam_type", "") or "").upper()
        is_central = (
            stored_type == "CENTRAL"
            or label.casefold() == "central"
            or label.casefold().startswith("central (")
        )

        explicit_choices = normalize_choices(
            result.student.department_choices if result.student_id else []
        )
        if explicit_choices:
            snapshot = explicit_choices
        elif not is_central:
            scheduled_department_id = department_lookup.get(label.casefold())
            if not scheduled_department_id:
                scheduled_department_id = result.department_id
            snapshot = (
                [{"department_id": scheduled_department_id, "priority": 1}]
                if scheduled_department_id
                else []
            )
        else:
            snapshot = []

        result.department_choices_snapshot = snapshot
        pending_updates.append(result)
        if len(pending_updates) >= 500:
            AdmissionResult.objects.bulk_update(
                pending_updates, ["department_choices_snapshot"], batch_size=500
            )
            pending_updates = []

    if pending_updates:
        AdmissionResult.objects.bulk_update(
            pending_updates, ["department_choices_snapshot"], batch_size=500
        )


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0061_admissionresult_waiting_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="admissionresult",
            name="department_choices_snapshot",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Department choices used for this result. Legacy Scheduled exams "
                    "without choices receive their exam department as priority 1."
                ),
            ),
        ),
        migrations.RunPython(backfill_choice_snapshots, migrations.RunPython.noop),
    ]
