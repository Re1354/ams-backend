"""REST API used by the watcher in the student exam portal.

Students have no AMS admin login, so these views take no JWT: a session is
authorized by its own random token (X-Proctor-Token), and starting one requires
an assigned exam with an open window.
"""
import hmac
import json
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from mainapp.models import Exam, Students

from . import services
from .models import ProctorSession, UnlockEvent

JPEG_MAGIC = b"\xff\xd8"
PNG_MAGIC = b"\x89PNG"
MAX_SNAPSHOT_BYTES = 1_048_576


def _error(message: str, code: int, **extra) -> Response:
    return Response({"detail": message, **extra}, status=code)


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _session_body(session: ProctorSession) -> dict:
    return {
        "session_id": session.pk,
        "token": session.token,
        "flag_count": session.flag_count,
        "status": session.status,
        "reported": session.is_reported,
        "report_after": services.REPORT_AFTER_FLAGS,
    }


def _authorized_session(request, session_id: int) -> ProctorSession | Response:
    session = get_object_or_404(ProctorSession, pk=session_id)
    supplied = request.headers.get("X-Proctor-Token", "")
    if not hmac.compare_digest(supplied.encode(), session.token.encode()):
        return _error("Invalid proctoring token.", status.HTTP_403_FORBIDDEN)
    return session


class StudentView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]


class StartSessionView(StudentView):
    parser_classes = [JSONParser, FormParser]

    def post(self, request):
        student_id = _int(request.data.get("student_id"))
        exam_id = _int(request.data.get("exam_id"))
        if student_id is None or exam_id is None:
            return _error("student_id and exam_id are required numbers.", status.HTTP_400_BAD_REQUEST)
        student = Students.objects.filter(pk=student_id).first()
        exam = Exam.objects.filter(pk=exam_id).first()
        if student is None or exam is None:
            return _error("This exam is not open for this student.", status.HTTP_403_FORBIDDEN)
        consent_at = None
        if request.data.get("consent_at"):
            consent_at = parse_datetime(str(request.data.get("consent_at")))
        try:
            session, created = services.start_or_resume(
                student=student,
                exam=exam,
                user_agent=request.headers.get("User-Agent", ""),
                consent_at=consent_at,
            )
        except services.SessionFinished as exc:
            return _error(str(exc), status.HTTP_409_CONFLICT)
        except services.NotAllowed as exc:
            return _error(str(exc), status.HTTP_403_FORBIDDEN)
        return Response(_session_body(session), status=201 if created else 200)


class FlagView(StudentView):
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, session_id: int):
        session = _authorized_session(request, session_id)
        if isinstance(session, Response):
            return session

        code = str(request.data.get("code") or "")
        if code not in services.ALL_CODES:
            return _error(f"Unknown flag code: {code or '(empty)'}.", status.HTTP_400_BAD_REQUEST)

        raw_detail = request.data.get("detail") or "{}"
        try:
            detail = json.loads(raw_detail) if isinstance(raw_detail, str) else dict(raw_detail)
            if not isinstance(detail, dict):
                raise ValueError
        except (ValueError, TypeError):
            return _error("detail must be a JSON object.", status.HTTP_400_BAD_REQUEST)

        snapshot_bytes = None
        upload = request.FILES.get("snapshot")
        if upload is not None:
            if upload.size > MAX_SNAPSHOT_BYTES:
                return _error("Snapshot is larger than 1 MB.", status.HTTP_400_BAD_REQUEST)
            snapshot_bytes = upload.read()
            if not (snapshot_bytes.startswith(JPEG_MAGIC) or snapshot_bytes.startswith(PNG_MAGIC)):
                return _error("Snapshot must be a JPEG or PNG image.", status.HTTP_400_BAD_REQUEST)

        occurred_at = None
        raw_age = request.data.get("age_ms")
        raw_time = request.data.get("occurred_at")
        if raw_age not in (None, ""):
            # Preferred: how long ago it happened, so the server clock sets the time
            # even when the exam PC's clock is wrong.
            age_ms = _int(str(raw_age))
            if age_ms is None or age_ms < 0:
                return _error("age_ms must be a whole number of milliseconds, 0 or more.", status.HTTP_400_BAD_REQUEST)
            occurred_at = timezone.now() - timedelta(milliseconds=age_ms)
        elif raw_time:
            occurred_at = parse_datetime(str(raw_time))
            if occurred_at is None:
                return _error("occurred_at must be an ISO date-time.", status.HTTP_400_BAD_REQUEST)

        try:
            flag = services.record_flag(session, code, detail, snapshot_bytes, occurred_at)
        except services.SessionFinished as exc:
            return _error(str(exc), status.HTTP_409_CONFLICT)

        return Response(
            {"flag_count": session.flag_count, "reported": session.is_reported, "counted": flag.counted},
            status=status.HTTP_201_CREATED,
        )


class EndSessionView(StudentView):
    parser_classes = [JSONParser, FormParser]

    def post(self, request, session_id: int):
        session = _authorized_session(request, session_id)
        if isinstance(session, Response):
            return session
        session = services.end_session(session)
        return Response({"status": session.status})


class UnlockView(StudentView):
    parser_classes = [JSONParser, FormParser]

    def post(self, request):
        student = Students.objects.filter(pk=_int(request.data.get("student_id"))).first()
        purpose = str(request.data.get("purpose") or "")
        code = str(request.data.get("code") or "")
        if student is None or purpose not in dict(UnlockEvent.PURPOSE_CHOICES) or not code:
            return _error("student_id, code and a valid purpose are required.", status.HTTP_400_BAD_REQUEST)
        session = None
        session_id = _int(request.data.get("session_id"))
        if session_id is not None:
            session = ProctorSession.objects.filter(pk=session_id, student=student).first()
        try:
            services.check_unlock(student, code, purpose, session)
        except services.UnlockNotSet:
            return Response(
                {"ok": False, "not_set": True, "detail": "No support unlock code has been set."},
                status=status.HTTP_409_CONFLICT,
            )
        except services.UnlockLocked as exc:
            return Response(
                {"ok": False, "locked_seconds": exc.seconds_left, "detail": "Too many wrong codes. Try again later."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except services.WrongUnlockCode as exc:
            return Response(
                {"ok": False, "tries_left": exc.tries_left, "detail": "Wrong code."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"ok": True, "purpose": purpose})
