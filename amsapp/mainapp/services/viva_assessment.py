from __future__ import annotations

from typing import Any

from ..models import Department, VivaAssignment, VivaRubrics
from ..models.viva_marks import VivaMarks


def resolve_department_for_exam(exam) -> Department | None:
    return Department.objects.filter(
        department_shortname__iexact=exam.department
    ).first() or Department.objects.filter(
        department_name__iexact=exam.department
    ).first()


def build_rubric_snapshot_for_department(department: Department | None) -> list[dict[str, Any]]:
    if not department:
        return []

    snapshot: list[dict[str, Any]] = []
    for rubric in VivaRubrics.objects.filter(department=department).order_by("id"):
        snapshot.append(
            {
                "source_rubric_id": rubric.id,
                "criteria": rubric.rubrics,
                "max_marks": float(rubric.marks or 0),
            }
        )
    return snapshot


def get_viva_assignment_for_student_exam(student, exam, teacher=None) -> VivaAssignment | None:
    assignments = VivaAssignment.objects.select_related("teacher", "student", "exam").filter(
        student=student,
        exam=exam,
    )
    if teacher is not None:
        assignments = assignments.filter(teacher=teacher)

    return assignments.order_by("-updated_at", "-created_at", "-id").first()


def ensure_viva_assignment_snapshot(viva_assignment: VivaAssignment, save: bool = True) -> VivaAssignment:
    if viva_assignment.rubric_snapshot:
        return viva_assignment

    department = resolve_department_for_exam(viva_assignment.exam)
    viva_assignment.rubric_snapshot = build_rubric_snapshot_for_department(department)
    if save:
        viva_assignment.save(update_fields=["rubric_snapshot", "updated_at"])
    return viva_assignment


def sync_legacy_viva_marks_to_assignment(
    viva_assignment: VivaAssignment,
    save: bool = True,
) -> VivaAssignment:
    try:
        legacy_marks = VivaMarks.objects.get(student=viva_assignment.student)
    except VivaMarks.DoesNotExist:
        return ensure_viva_assignment_snapshot(viva_assignment, save=save)

    ensure_viva_assignment_snapshot(viva_assignment, save=False)

    if not viva_assignment.total_marks:
        viva_assignment.total_marks = float(legacy_marks.marks or 0)
    if not viva_assignment.rubric_scores:
        viva_assignment.rubric_scores = legacy_marks.rubrics_marks or {}
    if not viva_assignment.remarks and legacy_marks.remarks:
        viva_assignment.remarks = legacy_marks.remarks

    if save:
        viva_assignment.save(
            update_fields=[
                "total_marks",
                "rubric_snapshot",
                "rubric_scores",
                "remarks",
                "updated_at",
            ]
        )
    return viva_assignment


def get_viva_assessment_for_student_exam(student, exam, teacher=None) -> VivaAssignment | None:
    viva_assignment = get_viva_assignment_for_student_exam(student, exam, teacher=teacher)
    if not viva_assignment:
        return None
    return sync_legacy_viva_marks_to_assignment(viva_assignment)


def build_viva_rubric_rows(viva_assignment: VivaAssignment | None) -> list[dict[str, Any]]:
    if not viva_assignment:
        return []

    snapshot = viva_assignment.rubric_snapshot or []
    scores = viva_assignment.rubric_scores or {}
    rows: list[dict[str, Any]] = []

    for index, rubric in enumerate(snapshot, start=1):
        rubric_id = rubric.get("source_rubric_id")
        score = scores.get(str(rubric_id))
        if score is None and rubric_id is not None:
            score = scores.get(rubric_id)

        rows.append(
            {
                "sl": index,
                "source_rubric_id": rubric_id,
                "criteria": rubric.get("criteria", ""),
                "max_marks": float(rubric.get("max_marks", 0) or 0),
                "awarded_marks": float(score or 0),
            }
        )

    return rows
