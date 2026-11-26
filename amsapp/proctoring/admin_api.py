"""Proctoring menu API for the AMS admin portal.

Access: JWT login + the role's permissions on the "/proctoring" menu
(read to view; edit or write to ban, unban and set the unlock code), limited to
the user's department/faculty scope like the result boards.
"""
from django.db import transaction
from django.db.models import BooleanField, Case, Exists, ExpressionWrapper, IntegerField, OuterRef, Q, Value, When
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from mainapp.authentication import CustomJWTAuthentication
from mainapp.models import AdmissionResult
from mainapp.permissions import has_menu_permission
from mainapp.services.access_control import get_user_access_scope

from . import conduct, services
from .models import Flag, ProctoringBan, ProctorSession, UnlockCode

MENU_LINK = "/proctoring"
MIN_UNLOCK_CODE_LENGTH = 6


class SessionPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def _can_read(user) -> bool:
    return has_menu_permission(user, MENU_LINK, "read") or _can_edit(user)


def _can_edit(user) -> bool:
    return has_menu_permission(user, MENU_LINK, "edit") or has_menu_permission(user, MENU_LINK, "write")


def _actor(request):
    """The AMS User row behind the JWT wrapper (CustomUser)."""
    return getattr(request.user, "custom_user", request.user)


def _forbidden(message="You do not have access to the Proctoring menu.") -> Response:
    return Response({"success": False, "message": message}, status=status.HTTP_403_FORBIDDEN)


def _admitted_exists():
    return Exists(
        AdmissionResult.objects.filter(
            student=OuterRef("student"),
            exam__semester__iexact=OuterRef("exam__semester"),
            is_admitted=True,
        )
    )


def _sessions_for(user):
    queryset = (
        ProctorSession.objects.select_related("student", "exam")
        .annotate(is_banned=conduct.active_ban_exists(), is_admitted=_admitted_exists())
    )
    return conduct.scope_sessions(queryset, get_user_access_scope(user))


def _conduct_of(session) -> str:
    if session.is_banned:
        return conduct.BANNED
    if session.is_reported:
        return conduct.REPORTED
    # Taken without camera (support code): never "clear".
    return conduct.NOT_MONITORED if session.camera_off else conduct.CLEAR


def _row(session) -> dict:
    student, exam = session.student, session.exam
    return {
        "id": session.id,
        "student": {
            "id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "f_id": student.f_id,
            "department_shortname": student.department_shortname,
        },
        "exam": {
            "id": exam.id,
            "department": exam.department,
            "semester": exam.semester,
            "faculty": exam.faculty,
        },
        "status": session.status,
        "flag_count": session.flag_count,
        "conduct": _conduct_of(session),
        "camera_off": session.camera_off,
        "admitted": bool(session.is_admitted),
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "reported_at": session.reported_at,
    }


def _ban_row(ban: ProctoringBan) -> dict:
    return {
        "id": ban.id,
        "exam_id": ban.exam_id,
        "reason": ban.reason,
        "banned_by": ban.banned_by.username if ban.banned_by else None,
        "banned_at": ban.banned_at,
        "lifted_at": ban.lifted_at,
        "lifted_by": ban.lifted_by.username if ban.lifted_by else None,
        "lift_reason": ban.lift_reason,
    }


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def session_list(request):
    if not _can_read(request.user):
        return _forbidden()
    params = request.query_params
    queryset = _sessions_for(request.user)

    semester = conduct.semester_key(params.get("semester"))
    if semester:
        queryset = queryset.filter(exam__semester__iexact=semester)
    if params.get("exam_id"):
        queryset = queryset.filter(exam_id=services_int(params.get("exam_id")))
    if params.get("department_id"):
        queryset = queryset.filter(conduct.student_scope_q([services_int(params.get("department_id"))]))
    search = (params.get("search") or "").strip()
    if search:
        queryset = queryset.filter(
            Q(student__full_name__icontains=search)
            | Q(student__username__icontains=search)
            | Q(student__f_id__icontains=search)
        )
    wanted = params.get("conduct")
    if wanted == conduct.BANNED:
        queryset = queryset.filter(is_banned=True)
    elif wanted == conduct.REPORTED:
        queryset = queryset.filter(is_banned=False, reported_at__isnull=False)
    elif wanted == conduct.CLEAR:
        queryset = queryset.filter(is_banned=False, reported_at__isnull=True, camera_off=False)
    elif wanted == conduct.NOT_MONITORED:
        queryset = queryset.filter(is_banned=False, reported_at__isnull=True, camera_off=True)
    elif wanted == "live":
        queryset = queryset.filter(status=ProctorSession.STATUS_ACTIVE)

    paginator = SessionPagination()
    page = paginator.paginate_queryset(_ordered(queryset, params.get("ordering")), request)
    return paginator.get_paginated_response([_row(s) for s in page])


def services_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


# Sort choices on the Proctoring page. Unknown values fall back to "conduct".
ORDERINGS = {
    "newest": ("-started_at", "-id"),
    "oldest": ("started_at", "id"),
    "serial_asc": ("student__f_id", "-started_at", "id"),
    "serial_desc": ("-student__f_id", "-started_at", "-id"),
    "name_asc": ("student__full_name", "student__username", "-started_at", "id"),
    "name_desc": ("-student__full_name", "-student__username", "-started_at", "-id"),
    "flags_desc": ("-flag_count", "-started_at", "-id"),
    "flags_asc": ("flag_count", "-started_at", "-id"),
}


def _ordered(queryset, ordering):
    if ordering in ORDERINGS:
        return queryset.order_by(*ORDERINGS[ordering])
    # Most serious first: banned, reported, not monitored, clear; newest first within each.
    return queryset.annotate(
        _rank=Case(
            When(is_banned=True, then=Value(0)),
            When(reported_at__isnull=False, then=Value(1)),
            When(camera_off=True, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).order_by("_rank", "-started_at", "-id")


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def session_detail(request, session_id: int):
    if not _can_read(request.user):
        return _forbidden()
    session = _sessions_for(request.user).filter(pk=session_id).first()
    if session is None:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    body = _row(session)
    body.update(
        {
            "consent_at": session.consent_at,
            "user_agent": session.user_agent,
            "flags": [
                {
                    "id": flag.id,
                    "code": flag.code,
                    "counted": flag.counted,
                    "detail": flag.detail,
                    "occurred_at": flag.occurred_at,
                    "has_snapshot": flag.has_snapshot,
                }
                for flag in session.flags.annotate(
                    has_snapshot=ExpressionWrapper(Q(snapshot__isnull=False), output_field=BooleanField())
                ).defer("snapshot")
            ],
            "unlock_events": [
                {"id": e.id, "purpose": e.purpose, "created_at": e.created_at} for e in session.unlock_events.all()
            ],
            "bans": [
                _ban_row(ban)
                for ban in ProctoringBan.objects.filter(
                    student=session.student, exam__semester__iexact=session.exam.semester
                ).select_related("banned_by", "lifted_by")
            ],
        }
    )
    return Response(body)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def flag_snapshot(request, flag_id: int):
    if not _can_read(request.user):
        return _forbidden()
    flag = Flag.objects.filter(pk=flag_id, snapshot__isnull=False).first()
    if flag is None or not _sessions_for(request.user).filter(pk=flag.session_id).exists():
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
    response = HttpResponse(bytes(flag.snapshot), content_type=flag.snapshot_type)
    response["Cache-Control"] = "private, max-age=3600"
    return response


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def summary(request):
    if not _can_read(request.user):
        return _forbidden()
    sessions = _sessions_for(request.user)
    return Response(
        {
            "reported_ids": list(
                sessions.filter(reported_at__isnull=False).order_by("reported_at").values_list("id", flat=True)
            ),
            "active_count": sessions.filter(status=ProctorSession.STATUS_ACTIVE).count(),
        }
    )


def _results_in_semester(student, exam):
    return AdmissionResult.objects.filter(
        student=student, exam__semester__iexact=exam.semester
    ).select_related("configuration", "configuration__department")


def _reapply(configurations) -> None:
    """Re-run the existing status allocation for each affected department + semester."""
    from mainapp.services.admission_calculator import (
        apply_semester_result_statuses,
        get_threshold_mapping_for_semester,
        is_configuration_complete,
    )

    for configuration in configurations:
        mapping = get_threshold_mapping_for_semester(configuration.department, configuration.semester)
        if not is_configuration_complete(mapping):
            continue
        apply_semester_result_statuses(
            department=configuration.department,
            semester=configuration.semester,
            threshold_value=mapping.min_threshold_mark,
            seat_limit=mapping.seat_limit,
            waiting_student_limit=mapping.waiting_student_limit,
        )


def _selected_sessions(request):
    ids = request.data.get("session_ids") or []
    if not isinstance(ids, list):
        return None
    ids = [services_int(i) for i in ids]
    return list(_sessions_for(request.user).filter(pk__in=ids).order_by("id"))


def _reason(request) -> str:
    return str(request.data.get("reason") or "").strip()


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def ban(request):
    if not _can_edit(request.user):
        return _forbidden("You need edit access on the Proctoring menu to ban students.")
    reason = _reason(request)
    sessions = _selected_sessions(request)
    if sessions is None or not reason:
        return Response(
            {"success": False, "message": "Select students and give a reason for the ban."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    banned, skipped_admitted, already = [], [], []
    configurations = {}
    for session in sessions:
        if session.is_admitted:
            skipped_admitted.append(session.student.username)
            continue
        if session.is_banned:
            already.append(session.id)
            continue
        with transaction.atomic():
            ProctoringBan.objects.create(
                student=session.student, exam=session.exam, reason=reason, banned_by=_actor(request)
            )
            for result in _results_in_semester(session.student, session.exam):
                if result.is_override_accepted and not result.is_admitted:
                    # A ban beats an earlier manual accept (not an admission; those are refused above).
                    result.is_override_accepted = False
                    result.accepted_at = None
                    result.acceptance_snapshot = {}
                    result.save(
                        update_fields=["is_override_accepted", "accepted_at", "acceptance_snapshot", "updated_at"]
                    )
                if result.configuration_id:
                    configurations[result.configuration_id] = result.configuration
        banned.append(session.id)
    _reapply(configurations.values())
    message = f"Banned {len(banned)} student(s)."
    if skipped_admitted:
        message += " Already admitted; cannot be banned: " + ", ".join(skipped_admitted) + "."
    return Response(
        {
            "success": True,
            "message": message,
            "banned": banned,
            "skipped_admitted": skipped_admitted,
            "already_banned": already,
        }
    )


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def unban(request):
    if not _can_edit(request.user):
        return _forbidden("You need edit access on the Proctoring menu to unban students.")
    reason = _reason(request)
    sessions = _selected_sessions(request)
    if sessions is None or not reason:
        return Response(
            {"success": False, "message": "Select students and give a reason."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    unbanned = []
    configurations = {}
    now = timezone.now()
    for session in sessions:
        lifted = ProctoringBan.objects.filter(
            student=session.student,
            exam__semester__iexact=session.exam.semester,
            lifted_at__isnull=True,
        ).update(lifted_at=now, lifted_by=_actor(request), lift_reason=reason)
        if not lifted:
            continue
        unbanned.append(session.id)
        for result in _results_in_semester(session.student, session.exam):
            if result.configuration_id:
                configurations[result.configuration_id] = result.configuration
    _reapply(configurations.values())
    return Response({"success": True, "message": f"Unbanned {len(unbanned)} student(s).", "unbanned": unbanned})


@api_view(["GET", "POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def unlock_code(request):
    if request.method == "GET":
        if not _can_read(request.user):
            return _forbidden()
        stored = UnlockCode.objects.filter(pk=1).select_related("changed_by").first()
        return Response(
            {
                "is_set": stored is not None,
                "changed_at": stored.changed_at if stored else None,
                "changed_by": stored.changed_by.username if stored and stored.changed_by else None,
            }
        )
    if not _can_edit(request.user):
        return _forbidden("You need edit access on the Proctoring menu to change the unlock code.")
    code = str(request.data.get("code") or "").strip()
    if len(code) < MIN_UNLOCK_CODE_LENGTH:
        return Response(
            {"success": False, "message": f"The code must have at least {MIN_UNLOCK_CODE_LENGTH} characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    services.set_unlock_code(code, _actor(request))
    return Response({"success": True, "message": "Support unlock code changed."})
