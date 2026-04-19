from datetime import datetime

from django.db import migrations, models
from django.utils import timezone


def build_snapshot(VivaRubrics, department):
    if not department:
        return []

    return [
        {
            "source_rubric_id": rubric.id,
            "criteria": rubric.rubrics,
            "max_marks": float(rubric.marks or 0),
        }
        for rubric in VivaRubrics.objects.filter(department=department).order_by("id")
    ]


def combine_created_date_and_time(created_at, time_value):
    if not created_at or not time_value:
        return None

    combined = datetime.combine(created_at.date(), time_value)
    if timezone.is_aware(created_at):
        return timezone.make_aware(combined, created_at.tzinfo or timezone.get_current_timezone())
    return combined


def backfill_viva_assignment_snapshot(apps, schema_editor):
    Department = apps.get_model("mainapp", "Department")
    VivaAssignment = apps.get_model("mainapp", "VivaAssignment")
    VivaMarks = apps.get_model("mainapp", "VivaMarks")
    VivaRubrics = apps.get_model("mainapp", "VivaRubrics")

    for assignment in VivaAssignment.objects.select_related("exam").all():
        department = Department.objects.filter(
            department_shortname__iexact=assignment.exam.department
        ).first() or Department.objects.filter(
            department_name__iexact=assignment.exam.department
        ).first()

        update_fields = []
        if not assignment.scheduled_at:
            assignment.scheduled_at = combine_created_date_and_time(
                assignment.created_at,
                assignment.time,
            )
            if assignment.scheduled_at:
                update_fields.append("scheduled_at")

        if not assignment.rubric_snapshot:
            assignment.rubric_snapshot = build_snapshot(VivaRubrics, department)
            update_fields.append("rubric_snapshot")

        legacy_marks = VivaMarks.objects.filter(student_id=assignment.student_id).first()
        if legacy_marks:
            if not assignment.total_marks:
                assignment.total_marks = float(legacy_marks.marks or 0)
                update_fields.append("total_marks")
            if not assignment.rubric_scores:
                assignment.rubric_scores = legacy_marks.rubrics_marks or {}
                update_fields.append("rubric_scores")
            if not assignment.remarks and legacy_marks.remarks:
                assignment.remarks = legacy_marks.remarks
                update_fields.append("remarks")

        if update_fields:
            assignment.save(update_fields=update_fields + ["updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0038_recalculate_submission_correctness"),
    ]

    operations = [
        migrations.AddField(
            model_name="vivaassignment",
            name="remarks",
            field=models.TextField(blank=True, null=True, help_text="Viva remarks for this exam"),
        ),
        migrations.AddField(
            model_name="vivaassignment",
            name="rubric_scores",
            field=models.JSONField(blank=True, default=dict, help_text="Awarded rubric scores keyed by rubric snapshot/source identifiers"),
        ),
        migrations.AddField(
            model_name="vivaassignment",
            name="rubric_snapshot",
            field=models.JSONField(blank=True, default=list, help_text="Snapshot of the viva rubrics used for this student's exam"),
        ),
        migrations.AddField(
            model_name="vivaassignment",
            name="scheduled_at",
            field=models.DateTimeField(blank=True, help_text="Scheduled date and time for the viva", null=True),
        ),
        migrations.AddField(
            model_name="vivaassignment",
            name="total_marks",
            field=models.FloatField(default=0.0, help_text="Total viva marks for this exam"),
        ),
        migrations.AddField(
            model_name="vivaassignment",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, default=timezone.now),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_viva_assignment_snapshot, migrations.RunPython.noop),
    ]

