"""Exam conduct status and ban lookups shared by the Proctoring menu and AMS results."""
from collections.abc import Iterable

from django.db.models import Exists, OuterRef, Q

from mainapp.models import Department
from mainapp.utils import normalize_semester_filter

from .models import ProctoringBan, ProctorSession

CLEAR = "clear"
REPORTED = "reported"
BANNED = "banned"
NOT_MONITORED = "not_monitored"


def semester_key(value) -> str:
    return (normalize_semester_filter(value) or "").lower()


def active_ban_student_ids(exams: Iterable) -> set[int]:
    """Students with an active ban on any exam in the same semester as one of `exams`."""
    semesters = {semester_key(exam.semester) for exam in exams}
    if not semesters:
        return set()
    bans = ProctoringBan.objects.filter(lifted_at__isnull=True).select_related("exam")
    return {ban.student_id for ban in bans if semester_key(ban.exam.semester) in semesters}


def active_ban_exists():
    """Subquery for annotating sessions: an active ban on this student in this exam's semester."""
    return Exists(
        ProctoringBan.objects.filter(
            student=OuterRef("student"),
            lifted_at__isnull=True,
            exam__semester__iexact=OuterRef("exam__semester"),
        )
    )


def conduct_for(student_ids: Iterable[int], exams: Iterable) -> dict[tuple[int, int], dict]:
    """Conduct per (student_id, exam_id) for result boards.

    Banned wins; otherwise the latest session decides reported/clear; no session
    means not monitored (never "clear").
    """
    student_ids = set(student_ids)
    exams = list(exams)
    exam_ids = {exam.id for exam in exams}
    banned_students = active_ban_student_ids(exams) & student_ids
    banned_semesters: dict[int, set[str]] = {}
    for ban in ProctoringBan.objects.filter(
        lifted_at__isnull=True, student_id__in=banned_students
    ).select_related("exam"):
        banned_semesters.setdefault(ban.student_id, set()).add(semester_key(ban.exam.semester))

    sessions = {}
    for session in ProctorSession.objects.filter(
        student_id__in=student_ids, exam_id__in=exam_ids
    ).order_by("started_at", "id"):
        sessions[(session.student_id, session.exam_id)] = session  # latest wins

    out = {}
    for exam in exams:
        sem = semester_key(exam.semester)
        for student_id in student_ids:
            session = sessions.get((student_id, exam.id))
            if sem in banned_semesters.get(student_id, set()):
                status = BANNED
            elif session is None:
                status = NOT_MONITORED
            elif session.is_reported:
                status = REPORTED
            else:
                status = CLEAR
            out[(student_id, exam.id)] = {
                "status": status,
                "flag_count": session.flag_count if session else 0,
                "session_id": session.id if session else None,
            }
    return out


def student_scope_q(department_ids: Iterable[int], prefix: str = "student__") -> Q:
    """Students who chose (or, without choices, belong to) one of the departments.

    Mirrors the student part of mainapp's build_department_results_filter.
    """
    ids = [int(d) for d in department_ids]
    q = Q(pk__in=[])
    for department_id in ids:
        q |= Q(**{f"{prefix}department_choices__contains": [{"department_id": department_id}]})
    shortnames = list(Department.objects.filter(id__in=ids).values_list("department_shortname", flat=True))
    if shortnames:
        q |= (
            Q(**{f"{prefix}department_choices": []}) | Q(**{f"{prefix}department_choices__isnull": True})
        ) & Q(**{f"{prefix}department_shortname__in": shortnames})
    return q


def scope_sessions(queryset, scope: dict):
    if scope.get("is_global"):
        return queryset
    return queryset.filter(student_scope_q(scope.get("department_ids") or []))
