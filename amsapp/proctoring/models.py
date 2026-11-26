"""Proctoring data: sessions, flags, bans and the support unlock code.

All tables are new (prefix proctoring_). Nothing here changes existing AMS tables.
"""
from django.db import models
from django.db.models import Q

from mainapp.models import Exam, Students, User


class ProctorSession(models.Model):
    """One applicant sitting one exam under proctoring."""

    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"
    STATUS_CHOICES = [(STATUS_ACTIVE, "Active"), (STATUS_FINISHED, "Finished")]

    student = models.ForeignKey(Students, on_delete=models.CASCADE, related_name="proctor_sessions")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="proctor_sessions")
    token = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    flag_count = models.PositiveIntegerField(default=0)
    consent_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    reported_at = models.DateTimeField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    # The exam ran (at least partly) without a working camera: allowed by the support
    # code, or the camera was covered or disconnected (CAMERA_OFF flag). Never "clear".
    camera_off = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "exam"],
                condition=Q(status="active"),
                name="proctoring_one_active_session",
            )
        ]
        indexes = [models.Index(fields=["student", "exam"], name="proctoring_session_pair_idx")]

    @property
    def is_reported(self) -> bool:
        return self.reported_at is not None

    def __str__(self):
        return f"{self.student_id} - exam {self.exam_id}"


class Flag(models.Model):
    """One rule violation (or an uncounted event) with optional evidence."""

    session = models.ForeignKey(ProctorSession, on_delete=models.CASCADE, related_name="flags")
    code = models.CharField(max_length=32)
    counted = models.BooleanField(default=True)
    detail = models.JSONField(default=dict, blank=True)
    snapshot = models.BinaryField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at", "id"]

    @property
    def snapshot_type(self) -> str:
        data = bytes(self.snapshot or b"")
        return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"

    def __str__(self):
        return f"{self.code} @ {self.occurred_at:%H:%M:%S}"


class ProctoringBan(models.Model):
    """A ban decided in the Proctoring menu. Active while lifted_at is empty."""

    student = models.ForeignKey(Students, on_delete=models.CASCADE, related_name="proctoring_bans")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="proctoring_bans")
    reason = models.TextField()
    banned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="proctoring_bans_made"
    )
    banned_at = models.DateTimeField(auto_now_add=True)
    lifted_at = models.DateTimeField(null=True, blank=True)
    lifted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="proctoring_bans_lifted"
    )
    lift_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-banned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "exam"],
                condition=Q(lifted_at__isnull=True),
                name="proctoring_one_active_ban",
            )
        ]

    @property
    def is_active(self) -> bool:
        return self.lifted_at is None


class UnlockCode(models.Model):
    """The single support unlock code (stored only as a hash)."""

    code_hash = models.CharField(max_length=128)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now=True)


class UnlockAttempt(models.Model):
    """Wrong-code counter per student, so guessing is slowed down on the server."""

    student = models.OneToOneField(Students, on_delete=models.CASCADE, related_name="proctoring_unlock")
    failures = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)


class UnlockEvent(models.Model):
    """A successful support unlock on a student's PC."""

    PURPOSE_FULLSCREEN = "fullscreen"
    PURPOSE_CAMERA = "camera"
    PURPOSE_CHOICES = [(PURPOSE_FULLSCREEN, "Full screen lock off"), (PURPOSE_CAMERA, "Continue without camera")]

    student = models.ForeignKey(Students, on_delete=models.CASCADE, related_name="proctoring_unlock_events")
    session = models.ForeignKey(
        ProctorSession, on_delete=models.SET_NULL, null=True, blank=True, related_name="unlock_events"
    )
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
