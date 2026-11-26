"""Migration 0004: sessions recorded before the covered-camera rule get the same status as new ones."""
import importlib

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone

from proctoring import services
from proctoring.models import Flag, ProctorSession

from .factories import exam_window

backfill = importlib.import_module("proctoring.migrations.0004_camera_covered_backfill")


def old_session(*codes):
    """A session whose flags were saved before the rule existed (no camera_off, no report)."""
    student, exam, _ = exam_window()
    session = ProctorSession.objects.create(student=student, exam=exam, token=services.secrets.token_hex(20))
    for code in codes:
        Flag.objects.create(session=session, code=code, counted=code in services.COUNTED_CODES, occurred_at=timezone.now())
    ProctorSession.objects.filter(pk=session.pk).update(
        flag_count=sum(code in services.COUNTED_CODES for code in codes)
    )
    return session


class CameraCoveredBackfillTests(TestCase):
    def run_backfill(self):
        backfill.mark_camera_covered_sessions(django_apps, None)

    def test_covered_camera_with_another_flag_becomes_reported(self):
        session = old_session("LOOK_AWAY", "CAMERA_OFF")
        self.run_backfill()
        session.refresh_from_db()
        self.assertTrue(session.camera_off)
        second = Flag.objects.filter(session=session).order_by("id").last()
        self.assertEqual(session.reported_at, second.created_at)

    def test_covered_camera_alone_becomes_not_monitored(self):
        session = old_session("CAMERA_OFF", "PROCTORING_OFFLINE")
        self.run_backfill()
        session.refresh_from_db()
        self.assertTrue(session.camera_off)
        self.assertIsNone(session.reported_at)

    def test_sessions_without_camera_problem_and_existing_reports_are_untouched(self):
        plain = old_session("LOOK_AWAY", "TAB_SWITCH")
        reported = old_session("CAMERA_OFF", "LOOK_AWAY")
        earlier = timezone.now() - timezone.timedelta(hours=1)
        ProctorSession.objects.filter(pk=reported.pk).update(reported_at=earlier)
        self.run_backfill()
        self.run_backfill()
        plain.refresh_from_db()
        reported.refresh_from_db()
        self.assertFalse(plain.camera_off)
        self.assertIsNone(plain.reported_at)
        self.assertEqual(reported.reported_at, earlier)
