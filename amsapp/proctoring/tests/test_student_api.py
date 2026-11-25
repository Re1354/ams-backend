"""Student-facing proctoring API (called by the watcher on the exam page)."""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from proctoring import services
from proctoring.models import Flag, ProctorSession, UnlockAttempt, UnlockEvent

from .factories import TINY_JPEG, exam_window, make_exam, make_schedule, make_student, make_user

BASE = "/api/proctoring"


class ApiTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student, self.exam, self.schedule = exam_window()

    def start(self, **overrides):
        body = {"student_id": self.student.id, "exam_id": self.exam.id, **overrides}
        return self.client.post(f"{BASE}/sessions/start", body, format="json")

    def flag(self, session_id, token, code="LOOK_AWAY", **extra):
        return self.client.post(
            f"{BASE}/sessions/{session_id}/flags",
            {"code": code, **extra},
            format="multipart",
            HTTP_X_PROCTOR_TOKEN=token,
        )

    def end(self, session_id, token):
        return self.client.post(f"{BASE}/sessions/{session_id}/end", HTTP_X_PROCTOR_TOKEN=token)

    def started(self):
        body = self.start().json()
        return body["session_id"], body["token"]


class StartTests(ApiTestBase):
    def test_start_creates_session(self):
        res = self.start()
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(len(body["token"]), 40)
        self.assertEqual(body["flag_count"], 0)
        self.assertFalse(body["reported"])
        self.assertEqual(body["report_after"], 3)
        self.assertEqual(body["status"], "active")
        session = ProctorSession.objects.get(pk=body["session_id"])
        self.assertEqual(session.student_id, self.student.id)
        self.assertEqual(session.exam_id, self.exam.id)

    def test_start_resumes_active_session(self):
        first = self.start().json()
        res = self.start()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["session_id"], first["session_id"])
        self.assertEqual(res.json()["token"], first["token"])
        self.assertEqual(ProctorSession.objects.count(), 1)

    def test_start_after_finished_conflicts(self):
        sid, token = self.started()
        self.end(sid, token)
        self.assertEqual(self.start().status_code, 409)

    def test_start_requires_ids(self):
        res = self.client.post(f"{BASE}/sessions/start", {"student_id": "x"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_start_rejects_unassigned_student(self):
        other = make_student()
        res = self.start(student_id=other.id)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(ProctorSession.objects.count(), 0)

    def test_start_rejects_unknown_student_or_exam(self):
        self.assertEqual(self.start(student_id=999999).status_code, 403)
        self.assertEqual(self.start(exam_id=999999).status_code, 403)

    def test_start_rejects_closed_window(self):
        exam = make_exam()
        schedule = make_schedule(exam, start_offset_min=-120, end_offset_min=-60)
        from .factories import assign

        assign(self.student, exam, schedule)
        self.assertEqual(self.start(exam_id=exam.id).status_code, 403)

    def test_start_allowed_shortly_before_window(self):
        exam = make_exam()
        schedule = make_schedule(exam, start_offset_min=10, end_offset_min=70)
        from .factories import assign

        assign(self.student, exam, schedule)
        self.assertEqual(self.start(exam_id=exam.id).status_code, 201)

    def test_start_allows_resume_after_window_end_for_active_session(self):
        sid, _ = self.started()
        self.schedule.end_time = timezone.now() - timedelta(minutes=1)
        self.schedule.save()
        res = self.start()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["session_id"], sid)

    def test_start_stores_consent_time(self):
        when = timezone.now() - timedelta(minutes=3)
        self.start(consent_at=when.isoformat())
        stored = ProctorSession.objects.get().consent_at
        self.assertEqual(stored.replace(microsecond=0), when.replace(microsecond=0))


class FlagTests(ApiTestBase):
    def test_flag_requires_token(self):
        sid, _ = self.started()
        self.assertEqual(self.flag(sid, "0" * 40).status_code, 403)
        self.assertEqual(Flag.objects.count(), 0)

    def test_unknown_code_rejected(self):
        sid, token = self.started()
        self.assertEqual(self.flag(sid, token, code="FOO").status_code, 400)

    def test_flag_counts_and_reports_on_fourth(self):
        sid, token = self.started()
        for expected in (1, 2, 3):
            body = self.flag(sid, token).json()
            self.assertEqual(body["flag_count"], expected)
            self.assertFalse(body["reported"])
        res = self.flag(sid, token)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["flag_count"], 4)
        self.assertTrue(res.json()["reported"])
        self.assertIsNotNone(ProctorSession.objects.get(pk=sid).reported_at)

    def test_offline_entry_not_counted(self):
        sid, token = self.started()
        body = self.flag(sid, token, code="PROCTORING_OFFLINE").json()
        self.assertFalse(body["counted"])
        self.assertEqual(body["flag_count"], 0)

    def test_detail_json_stored(self):
        sid, token = self.started()
        self.flag(sid, token, detail='{"seconds": 5.2, "yawDeg": 41}')
        self.assertEqual(Flag.objects.get().detail, {"seconds": 5.2, "yawDeg": 41})

    def test_snapshot_stored(self):
        sid, token = self.started()
        snap = SimpleUploadedFile("s.jpg", TINY_JPEG, content_type="image/jpeg")
        self.assertEqual(self.flag(sid, token, snapshot=snap).status_code, 201)
        self.assertTrue(bytes(Flag.objects.get().snapshot).startswith(b"\xff\xd8"))

    def test_snapshot_too_large_or_fake_rejected(self):
        sid, token = self.started()
        big = SimpleUploadedFile("s.jpg", b"\xff\xd8" + b"0" * 1_048_575, content_type="image/jpeg")
        self.assertEqual(self.flag(sid, token, snapshot=big).status_code, 400)
        fake = SimpleUploadedFile("s.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.flag(sid, token, snapshot=fake).status_code, 400)
        self.assertEqual(Flag.objects.count(), 0)

    def test_occurred_at_clamped(self):
        sid, token = self.started()
        session = ProctorSession.objects.get(pk=sid)
        self.flag(sid, token, occurred_at="2000-01-01T00:00:00Z")
        self.flag(sid, token, occurred_at="2100-01-01T00:00:00Z")
        past, future = Flag.objects.order_by("id")
        self.assertEqual(past.occurred_at, session.started_at)
        self.assertLessEqual(future.occurred_at, timezone.now())

    def test_age_ms_uses_server_clock(self):
        sid, token = self.started()
        ProctorSession.objects.filter(pk=sid).update(started_at=timezone.now() - timedelta(minutes=1))
        self.flag(sid, token, occurred_at="2000-01-01T00:00:00Z", age_ms="2000")
        stored = Flag.objects.get().occurred_at
        self.assertLess(abs((stored - (timezone.now() - timedelta(seconds=2))).total_seconds()), 1.5)

    def test_bad_age_ms_rejected(self):
        sid, token = self.started()
        self.assertEqual(self.flag(sid, token, age_ms="soon").status_code, 400)
        self.assertEqual(self.flag(sid, token, age_ms="-5").status_code, 400)

    def test_flag_after_end_conflicts(self):
        sid, token = self.started()
        self.end(sid, token)
        self.assertEqual(self.flag(sid, token).status_code, 409)

    def test_flag_unknown_session_404(self):
        self.assertEqual(self.flag(99999, "0" * 40).status_code, 404)


class EndTests(ApiTestBase):
    def test_end_is_idempotent(self):
        sid, token = self.started()
        first = self.end(sid, token)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "finished")
        ended_at = ProctorSession.objects.get(pk=sid).ended_at
        self.assertEqual(self.end(sid, token).status_code, 200)
        self.assertEqual(ProctorSession.objects.get(pk=sid).ended_at, ended_at)

    def test_end_requires_token(self):
        sid, _ = self.started()
        self.assertEqual(self.end(sid, "0" * 40).status_code, 403)


class CorsTests(ApiTestBase):
    def test_cors_allows_proctor_token_header(self):
        res = self.client.options(
            f"{BASE}/sessions/start",
            HTTP_ORIGIN="http://localhost:3000",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-proctor-token",
        )
        self.assertIn("x-proctor-token", res["Access-Control-Allow-Headers"])


class UnlockTests(ApiTestBase):
    def unlock(self, code, purpose="fullscreen", **extra):
        body = {"student_id": self.student.id, "code": code, "purpose": purpose, **extra}
        return self.client.post(f"{BASE}/unlock", body, format="json")

    def test_unlock_without_code_set_returns_409(self):
        res = self.unlock("123456")
        self.assertEqual(res.status_code, 409)
        self.assertTrue(res.json()["not_set"])

    def test_unlock_correct_code_logs_event(self):
        services.set_unlock_code("support-2027", make_user())
        res = self.unlock("support-2027")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])
        event = UnlockEvent.objects.get()
        self.assertEqual(event.purpose, "fullscreen")
        self.assertIsNone(event.session_id)

    def test_unlock_correct_code_logs_event_and_uncounted_flag(self):
        services.set_unlock_code("support-2027", make_user())
        sid, _ = self.started()
        res = self.unlock("support-2027", purpose="camera", session_id=sid)
        self.assertEqual(res.status_code, 200)
        flag = Flag.objects.get()
        self.assertEqual(flag.code, "SUPPORT_UNLOCK")
        self.assertFalse(flag.counted)
        self.assertEqual(flag.detail, {"purpose": "camera"})
        self.assertEqual(ProctorSession.objects.get(pk=sid).flag_count, 0)

    def test_unlock_wrong_code_reports_tries_left(self):
        services.set_unlock_code("support-2027", make_user())
        res = self.unlock("wrong")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["tries_left"], 4)
        self.assertEqual(UnlockEvent.objects.count(), 0)

    def test_unlock_five_wrong_tries_locks_for_five_minutes(self):
        services.set_unlock_code("support-2027", make_user())
        for _ in range(5):
            self.unlock("wrong")
        res = self.unlock("support-2027")
        self.assertEqual(res.status_code, 429)
        self.assertGreater(res.json()["locked_seconds"], 290)
        UnlockAttempt.objects.filter(student=self.student).update(
            locked_until=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.unlock("support-2027").status_code, 200)

    def test_unlock_rejects_bad_purpose(self):
        services.set_unlock_code("support-2027", make_user())
        self.assertEqual(self.unlock("support-2027", purpose="everything").status_code, 400)
