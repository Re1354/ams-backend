"""
One-time cleanup for the duplicate / spurious-ABSENT bug.

A student may sit only one exam per semester, but AdmissionResult is unique per
(exam, student) and the board pools every exam in a semester. Before the
semester-scoped fixes landed, a student assigned to a stray second exam got an
extra row (usually stamped ABSENT once that exam's window closed), so the same
student surfaced twice and non-selected students appeared in the Absent tab.

The code changes stop NEW duplicates from being generated; this migration
removes the rows already written under the old per-exam logic so exactly one
AdmissionResult per student per semester remains.
"""

from collections import defaultdict

from django.db import migrations


def _semester_key(value):
    return (value or "").strip().lower()


def dedupe_admission_results(apps, schema_editor):
    AdmissionResult = apps.get_model("mainapp", "AdmissionResult")
    Exam = apps.get_model("mainapp", "Exam")
    Submission = apps.get_model("mainapp", "Submission")

    exam_semester = {
        exam_id: _semester_key(semester)
        for exam_id, semester in Exam.objects.values_list("id", "semester")
    }

    # (student_id, semester) pairs where the student submitted at least one exam.
    submitted_pairs = set()
    for student_id, exam_id in Submission.objects.values_list("student_id", "exam_id"):
        submitted_pairs.add((student_id, exam_semester.get(exam_id, "")))

    # Group every result by (student, semester-of-its-exam).
    groups = defaultdict(list)
    for result in AdmissionResult.objects.all():
        key = (result.student_id, exam_semester.get(result.exam_id, ""))
        groups[key].append(result)

    def survivor_rank(result):
        # Best survivor first: attended over absent, then higher weighted total,
        # then the most recently created row.
        return (
            1 if result.attended_exam else 0,
            result.weighted_total_marks or 0.0,
            result.created_at,
        )

    deleted = 0
    promoted = 0

    for (student_id, semester), rows in groups.items():
        if len(rows) > 1:
            rows.sort(key=survivor_rank, reverse=True)
            survivor = rows[0]
            losers = rows[1:]

            # Never drop an admitted / override seat: fold it onto the survivor.
            had_admitted = any(r.is_admitted for r in rows)
            had_override = any(r.is_override_accepted for r in rows)
            changed = False
            if had_admitted and not survivor.is_admitted:
                survivor.is_admitted = True
                changed = True
            if had_override and not survivor.is_override_accepted:
                survivor.is_override_accepted = True
                changed = True
            if (survivor.is_admitted or survivor.is_override_accepted) and (
                not survivor.is_selected or survivor.result_status != "SELECTED"
            ):
                survivor.is_selected = True
                survivor.result_status = "SELECTED"
                changed = True
            if changed:
                survivor.save()
                promoted += 1

            for loser in losers:
                loser.delete()
                deleted += 1

    # Residual: a lone ABSENT row for a student who actually submitted a
    # different exam in the same semester (the attended row was never written).
    # Drop it; the next recalc regenerates the correct row from the submission.
    for result in AdmissionResult.objects.filter(result_status="ABSENT"):
        key = (result.student_id, exam_semester.get(result.exam_id, ""))
        if not result.attended_exam and key in submitted_pairs:
            result.delete()
            deleted += 1

    print(
        f"  dedupe_admission_results: deleted {deleted} duplicate/stray row(s), "
        f"promoted {promoted} survivor(s) to keep admitted seats."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0049_alter_vivamarks_marks"),
    ]

    operations = [
        migrations.RunPython(dedupe_admission_results, migrations.RunPython.noop),
    ]
