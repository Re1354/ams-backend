"""Business rules: start/resume, flag counting, reporting, support unlock."""
import secrets
from datetime import datetime, timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from mainapp.models import Exam, StudentAssignTeacherExam, Students

from .models import Flag, ProctorSession, UnlockAttempt, UnlockCode, UnlockEvent

COUNTED_CODES = frozenset(
    {
        "LOOK_AWAY",
        "MULTIPLE_PEOPLE",
        "PHONE",
        "OTHER_DEVICE",
        "BOOK",
        "TAB_SWITCH",
        "FULLSCREEN_EXIT",
        "CAMERA_OFF",
        "LEFT_EXAM",
    }
)
ALL_CODES = COUNTED_CODES | {"PROCTORING_OFFLINE", "SUPPORT_UNLOCK"}

# A session is reported once its counted flags go above this number.
REPORT_AFTER_FLAGS = 3

# A session may start this long before the scheduled start (pre-exam countdown page).
EARLY_START = timedelta(minutes=15)

UNLOCK_MAX_FAILURES = 5
UNLOCK_LOCK_TIME = timedelta(minutes=5)


class SessionFinished(Exception):
    """The session (or the exam) is already finished."""


class NotAllowed(Exception):
    """The student is not assigned to this exam, or its window is not open."""


class UnlockLocked(Exception):
    def __init__(self, seconds_left: int):
        super().__init__("Too many wrong codes.")
        self.seconds_left = seconds_left


class UnlockNotSet(Exception):
    """No support unlock code has been set yet."""


class WrongUnlockCode(Exception):
    def __init__(self, tries_left: int):
        super().__init__("Wrong code.")
        self.tries_left = tries_left


def _window_open(student: Students, exam: Exam, now: datetime) -> bool:
    return StudentAssignTeacherExam.objects.filter(
        student=student,
        exam=exam,
        schedule__start_time__lte=now + EARLY_START,
        schedule__end_time__gt=now,
    ).exists()


def start_or_resume(
    student: Students,
    exam: Exam,
    user_agent: str,
    consent_at: datetime | None = None,
    camera_off: bool = False,
) -> tuple[ProctorSession, bool]:
    """Return the active session for this student+exam, creating one if allowed.

    Raises SessionFinished when the only sessions for this pair are finished, and
    NotAllowed when the student has no open exam window for this exam.
    """
    with transaction.atomic():
        active = (
            ProctorSession.objects.select_for_update()
            .filter(student=student, exam=exam, status=ProctorSession.STATUS_ACTIVE)
            .first()
        )
        if active:
            _attach_login_unlocks(active, consent_at)
            if camera_off:
                _mark_camera_off(active)
            return active, False
        if ProctorSession.objects.filter(student=student, exam=exam).exists():
            raise SessionFinished("This exam is already finished.")
        now = timezone.now()
        if not _window_open(student, exam, now):
            raise NotAllowed("This exam is not open for this student.")
        if consent_at is not None:
            consent_at = min(consent_at, now)
        session = ProctorSession.objects.create(
            student=student,
            exam=exam,
            consent_at=consent_at,
            user_agent=user_agent[:500],
            token=secrets.token_hex(20),
            camera_off=camera_off,
        )
        _attach_login_unlocks(session, consent_at)
        return session, True


# consent_at comes from the student's PC clock, which may run a little ahead of the server.
CONSENT_CLOCK_SLACK = timedelta(minutes=5)


def _attach_login_unlocks(session: ProctorSession, consent_at: datetime | None) -> None:
    """Support unlocks given in this login before the exam (they last until logout) belong in its report."""
    if consent_at is None:
        return
    pending = UnlockEvent.objects.filter(
        student_id=session.student_id, session__isnull=True, created_at__gte=consent_at - CONSENT_CLOCK_SLACK
    )
    if pending.filter(purpose=UnlockEvent.PURPOSE_CAMERA).exists():
        _mark_camera_off(session)
    pending.update(session=session)


def _mark_camera_off(session: ProctorSession) -> None:
    """Once without camera, the session stays "not monitored" (never set back)."""
    if not session.camera_off:
        ProctorSession.objects.filter(pk=session.pk).update(camera_off=True)
        session.camera_off = True


def _clamp(occurred_at: datetime | None, session: ProctorSession) -> datetime:
    now = timezone.now()
    if occurred_at is None:
        return now
    return min(max(occurred_at, session.started_at), now)


def record_flag(
    session: ProctorSession,
    code: str,
    detail: dict,
    snapshot_bytes: bytes | None,
    occurred_at: datetime | None,
) -> Flag:
    """Store a flag, update the count, and mark the session reported when needed."""
    with transaction.atomic():
        locked = ProctorSession.objects.select_for_update().get(pk=session.pk)
        if locked.status == ProctorSession.STATUS_FINISHED:
            raise SessionFinished("This exam is already finished.")
        counted = code in COUNTED_CODES
        flag = Flag.objects.create(
            session=locked,
            code=code,
            counted=counted,
            detail=detail,
            snapshot=snapshot_bytes,
            occurred_at=_clamp(occurred_at, locked),
        )
        if counted:
            locked.flag_count += 1
            if locked.flag_count > REPORT_AFTER_FLAGS and locked.reported_at is None:
                locked.reported_at = timezone.now()
            locked.save(update_fields=["flag_count", "reported_at"])
        session.flag_count = locked.flag_count
        session.reported_at = locked.reported_at
        return flag


def end_session(session: ProctorSession) -> ProctorSession:
    """Finish the session. Calling it again changes nothing."""
    with transaction.atomic():
        locked = ProctorSession.objects.select_for_update().get(pk=session.pk)
        if locked.status != ProctorSession.STATUS_FINISHED:
            locked.status = ProctorSession.STATUS_FINISHED
            locked.ended_at = timezone.now()
            locked.save(update_fields=["status", "ended_at"])
        return locked


def set_unlock_code(code: str, user) -> UnlockCode:
    obj, _ = UnlockCode.objects.update_or_create(
        pk=1, defaults={"code_hash": make_password(code), "changed_by": user}
    )
    return obj


def check_unlock(
    student: Students, code: str, purpose: str, session: ProctorSession | None = None
) -> UnlockEvent:
    """Verify the support code for this student's PC and log the unlock.

    Raises UnlockNotSet, UnlockLocked(seconds_left) or WrongUnlockCode(tries_left).
    """
    stored = UnlockCode.objects.filter(pk=1).first()
    if stored is None:
        raise UnlockNotSet()
    now = timezone.now()
    # Decide inside the transaction, raise after it, so a wrong try is saved (not rolled back).
    outcome: Exception | None = None
    with transaction.atomic():
        attempt, _ = UnlockAttempt.objects.select_for_update().get_or_create(student=student)
        if attempt.locked_until and attempt.locked_until > now:
            outcome = UnlockLocked(int((attempt.locked_until - now).total_seconds()) + 1)
        elif not check_password(code, stored.code_hash):
            if attempt.locked_until:  # an old lock has passed: start counting again
                attempt.failures = 0
                attempt.locked_until = None
            attempt.failures += 1
            if attempt.failures >= UNLOCK_MAX_FAILURES:
                attempt.locked_until = now + UNLOCK_LOCK_TIME
            attempt.save(update_fields=["failures", "locked_until"])
            outcome = WrongUnlockCode(max(0, UNLOCK_MAX_FAILURES - attempt.failures))
        else:
            attempt.failures = 0
            attempt.locked_until = None
            attempt.save(update_fields=["failures", "locked_until"])
    if outcome is not None:
        raise outcome
    event = UnlockEvent.objects.create(student=student, session=session, purpose=purpose)
    if session is not None and purpose == UnlockEvent.PURPOSE_CAMERA:
        _mark_camera_off(session)
    if session is not None and session.status == ProctorSession.STATUS_ACTIVE:
        record_flag(session, "SUPPORT_UNLOCK", {"purpose": purpose}, None, None)
    return event
