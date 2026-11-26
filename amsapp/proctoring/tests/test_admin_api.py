"""Admin (Proctoring menu) API: RBAC, department scope, list, detail, ban, unlock code."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from mainapp.models import AdmissionConfiguration, AdmissionResult, DepartmentThreshold
from proctoring import services
from proctoring.models import Flag, ProctoringBan, ProctorSession

from .factories import (
    TINY_JPEG,
    auth_header,
    exam_window,
    grant,
    make_department,
    make_student,
    make_user,
    assign,
)

ADMIN = "/api/proctoring/admin"


def make_session(student, exam, flags=0, reported=False, status="active", minutes_ago=0):
    session = ProctorSession.objects.create(
        student=student, exam=exam, token=services.secrets.token_hex(20), status=status
    )
    if minutes_ago:
        ProctorSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
    for _ in range(flags):
        services.record_flag(session, "LOOK_AWAY", {}, None, None)
    if reported and session.reported_at is None:
        ProctorSession.objects.filter(pk=session.pk).update(reported_at=timezone.now())
    session.refresh_from_db()
    return session


class AdminBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.superadmin = make_user("superadmin")
        self.cse = make_department("CSE")
        self.student, self.exam, self.schedule = exam_window(department="CSE")
        self.student.department_choices = [{"department_id": self.cse.id, "priority": 1}]
        self.student.save()
        self.session = make_session(self.student, self.exam, flags=1)

    def as_user(self, user):
        self.client.credentials(**auth_header(user))

    def get(self, path, user=None, **params):
        self.as_user(user or self.superadmin)
        return self.client.get(f"{ADMIN}{path}", params)

    def post(self, path, body, user=None):
        self.as_user(user or self.superadmin)
        return self.client.post(f"{ADMIN}{path}", body, format="json")


class PermissionTests(AdminBase):
    def test_list_requires_login(self):
        self.assertIn(self.client.get(f"{ADMIN}/sessions").status_code, (401, 403))

    def test_list_requires_menu_read_permission(self):
        clerk = make_user("clerk", is_global_access=True, access_type="GLOBAL")
        self.assertEqual(self.get("/sessions", user=clerk).status_code, 403)
        grant("clerk", read=True)
        self.assertEqual(self.get("/sessions", user=clerk).status_code, 200)

    def test_ban_requires_edit_permission(self):
        clerk = make_user("clerk2", is_global_access=True, access_type="GLOBAL")
        grant("clerk2", read=True)
        res = self.post("/ban", {"session_ids": [self.session.id], "reason": "cheating"}, user=clerk)
        self.assertEqual(res.status_code, 403)
        grant("clerk2", read=True, edit=True)
        res = self.post("/ban", {"session_ids": [self.session.id], "reason": "cheating"}, user=clerk)
        self.assertEqual(res.status_code, 200)

    def test_superadmin_bypasses(self):
        self.assertEqual(self.get("/sessions").status_code, 200)
        self.assertEqual(self.get(f"/sessions/{self.session.id}").status_code, 200)


class ListTests(AdminBase):
    def test_list_row_shape(self):
        row = self.get("/sessions").json()["results"][0]
        self.assertEqual(row["id"], self.session.id)
        self.assertEqual(row["student"]["id"], self.student.id)
        self.assertEqual(row["student"]["f_id"], self.student.f_id)
        self.assertEqual(row["exam"]["id"], self.exam.id)
        self.assertEqual(row["flag_count"], 1)
        self.assertEqual(row["conduct"], "clear")
        self.assertFalse(row["admitted"])
        self.assertEqual(row["status"], "active")

    def test_reported_first_then_newest(self):
        s2, e2, _ = exam_window()
        s3, e3, _ = exam_window()
        newest = make_session(s2, e2)
        reported_old = make_session(s3, e3, flags=4, minutes_ago=30)
        ids = [r["id"] for r in self.get("/sessions").json()["results"]]
        self.assertEqual(ids[0], reported_old.id)
        self.assertLess(ids.index(newest.id), ids.index(self.session.id))

    def test_list_filters_and_search(self):
        other, other_exam, _ = exam_window(semester="Spring 2027")
        other.full_name = "Karim Unique"
        other.save()
        make_session(other, other_exam, flags=4)
        self.assertEqual(self.get("/sessions", search="karim uni").json()["count"], 1)
        self.assertEqual(self.get("/sessions", search=other.f_id).json()["count"], 1)
        self.assertEqual(self.get("/sessions", semester="spring 2027").json()["count"], 1)
        self.assertEqual(self.get("/sessions", exam_id=self.exam.id).json()["count"], 1)
        self.assertEqual(self.get("/sessions", conduct="reported").json()["count"], 1)
        self.assertEqual(self.get("/sessions", conduct="clear").json()["count"], 1)
        self.assertEqual(self.get("/sessions", conduct="live").json()["count"], 2)
        self.post("/ban", {"session_ids": [self.session.id], "reason": "x"})
        self.assertEqual(self.get("/sessions", conduct="banned").json()["count"], 1)
        self.assertEqual(self.get("/sessions", conduct="clear").json()["count"], 0)

    def test_department_filter(self):
        swe = make_department("SWE")
        other, other_exam, _ = exam_window(department="SWE")
        other.department_choices = [{"department_id": swe.id, "priority": 1}]
        other.save()
        make_session(other, other_exam)
        ids = [r["student"]["id"] for r in self.get("/sessions", department_id=swe.id).json()["results"]]
        self.assertEqual(ids, [other.id])


class ScopeTests(AdminBase):
    def test_department_scope_hides_and_blocks_other_departments(self):
        swe = make_department("SWE")
        other, other_exam, _ = exam_window(department="SWE")
        other.department_choices = [{"department_id": swe.id, "priority": 1}]
        other.save()
        other_session = make_session(other, other_exam)
        flag = Flag.objects.create(
            session=other_session, code="LOOK_AWAY", snapshot=TINY_JPEG, occurred_at=timezone.now()
        )
        grant("cse_head", read=True, edit=True)
        cse_head = make_user("cse_head", access_type="DEPARTMENT", department_id=self.cse.id)

        ids = [r["id"] for r in self.get("/sessions", user=cse_head).json()["results"]]
        self.assertEqual(ids, [self.session.id])
        self.assertEqual(self.get(f"/sessions/{other_session.id}", user=cse_head).status_code, 404)
        self.assertEqual(self.get(f"/flags/{flag.id}/snapshot", user=cse_head).status_code, 404)
        res = self.post("/ban", {"session_ids": [other_session.id], "reason": "x"}, user=cse_head)
        self.assertEqual(res.json()["banned"], [])
        self.assertFalse(ProctoringBan.objects.exists())
        self.assertEqual(self.get("/summary", user=cse_head).json()["active_count"], 1)

    def test_exam_without_camera_shows_not_monitored_and_has_its_own_filter(self):
        ProctorSession.objects.filter(pk=self.session.pk).update(camera_off=True)
        other, other_exam, _ = exam_window()
        make_session(other, other_exam)
        row = next(r for r in self.get("/sessions").json()["results"] if r["id"] == self.session.id)
        self.assertEqual(row["conduct"], "not_monitored")
        self.assertTrue(row["camera_off"])
        self.assertEqual([r["id"] for r in self.get("/sessions", conduct="not_monitored").json()["results"]], [self.session.id])
        self.assertNotIn(self.session.id, [r["id"] for r in self.get("/sessions", conduct="clear").json()["results"]])

    def test_reported_wins_over_not_monitored(self):
        ProctorSession.objects.filter(pk=self.session.pk).update(camera_off=True, reported_at=timezone.now())
        row = self.get("/sessions").json()["results"][0]
        self.assertEqual(row["conduct"], "reported")
        self.assertEqual(self.get("/sessions", conduct="not_monitored").json()["count"], 0)


    def test_camera_covered_without_other_flags_is_not_monitored(self):
        other, other_exam, _ = exam_window()
        covered = make_session(other, other_exam)
        services.record_flag(covered, "CAMERA_OFF", {}, None, None)
        row = next(r for r in self.get("/sessions").json()["results"] if r["id"] == covered.id)
        self.assertEqual((row["conduct"], row["flag_count"]), ("not_monitored", 1))
        self.assertIn(covered.id, [r["id"] for r in self.get("/sessions", conduct="not_monitored").json()["results"]])

    def test_camera_covered_with_another_flag_is_reported(self):
        services.record_flag(self.session, "CAMERA_OFF", {}, None, None)  # self.session already has 1 flag
        row = next(r for r in self.get("/sessions").json()["results"] if r["id"] == self.session.id)
        self.assertEqual(row["conduct"], "reported")
        self.assertIn(self.session.id, [r["id"] for r in self.get("/sessions", conduct="reported").json()["results"]])


class SortTests(AdminBase):
    """`ordering` on the session list; the page shows 25 rows, so sorting happens on the server."""

    def setUp(self):
        super().setUp()
        self.student.full_name, self.student.f_id = "Dalia", "APP005"
        self.student.save()
        rows = {}
        for name, serial, flags, minutes in (("Bina", "APP003", 2, 30), ("Arif", "APP010", 0, 10), ("Chandra", "APP001", 3, 20)):
            student, exam, _ = exam_window()
            student.full_name, student.f_id = name, serial
            student.save()
            rows[name] = make_session(student, exam, flags=flags, minutes_ago=minutes)
        self.dalia, self.bina, self.arif, self.chandra = self.session, rows["Bina"], rows["Arif"], rows["Chandra"]

    def ids(self, **params):
        res = self.get("/sessions", **params)
        self.assertEqual(res.status_code, 200)
        return [r["id"] for r in res.json()["results"]]

    def names(self, *sessions):
        return [s.id for s in sessions]

    def test_by_date(self):
        self.assertEqual(self.ids(ordering="newest"), self.names(self.dalia, self.arif, self.chandra, self.bina))
        self.assertEqual(self.ids(ordering="oldest"), self.names(self.bina, self.chandra, self.arif, self.dalia))

    def test_by_application_serial(self):
        self.assertEqual(self.ids(ordering="serial_asc"), self.names(self.chandra, self.bina, self.dalia, self.arif))
        self.assertEqual(self.ids(ordering="serial_desc"), self.names(self.arif, self.dalia, self.bina, self.chandra))

    def test_by_name(self):
        self.assertEqual(self.ids(ordering="name_asc"), self.names(self.arif, self.bina, self.chandra, self.dalia))
        self.assertEqual(self.ids(ordering="name_desc"), self.names(self.dalia, self.chandra, self.bina, self.arif))

    def test_by_flags(self):
        self.assertEqual(self.ids(ordering="flags_desc"), self.names(self.chandra, self.bina, self.dalia, self.arif))
        self.assertEqual(self.ids(ordering="flags_asc"), self.names(self.arif, self.dalia, self.bina, self.chandra))

    def test_by_conduct_most_serious_first_is_the_default(self):
        self.post("/ban", {"session_ids": [self.arif.id], "reason": "x"})
        ProctorSession.objects.filter(pk=self.bina.pk).update(reported_at=timezone.now())
        ProctorSession.objects.filter(pk=self.chandra.pk).update(camera_off=True)
        expected = self.names(self.arif, self.bina, self.chandra, self.dalia)
        self.assertEqual(self.ids(ordering="conduct"), expected)
        self.assertEqual(self.ids(), expected)
        self.assertEqual(self.ids(ordering="nonsense"), expected)

    def test_sorting_keeps_filters(self):
        self.assertEqual(self.ids(ordering="name_asc", search="APP00"), self.names(self.bina, self.chandra, self.dalia))


class DetailTests(AdminBase):
    def test_detail_has_flags_events_and_bans(self):
        Flag.objects.create(session=self.session, code="TAB_SWITCH", snapshot=TINY_JPEG, occurred_at=timezone.now())
        body = self.get(f"/sessions/{self.session.id}").json()
        self.assertEqual(body["id"], self.session.id)
        self.assertEqual([f["code"] for f in body["flags"]], ["LOOK_AWAY", "TAB_SWITCH"])
        self.assertTrue(body["flags"][1]["has_snapshot"])
        self.assertFalse(body["flags"][0]["has_snapshot"])
        self.assertEqual(body["unlock_events"], [])
        self.assertEqual(body["bans"], [])
        self.assertIn("user_agent", body)
        self.assertIn("consent_at", body)
        self.assertFalse(body["camera_off"])

    def test_snapshot_returns_image_or_404(self):
        with_photo = Flag.objects.create(
            session=self.session, code="LOOK_AWAY", snapshot=TINY_JPEG, occurred_at=timezone.now()
        )
        without = self.session.flags.filter(snapshot__isnull=True).first()
        res = self.get(f"/flags/{with_photo.id}/snapshot")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/jpeg")
        self.assertEqual(self.get(f"/flags/{without.id}/snapshot").status_code, 404)

    def test_summary_lists_reported_ids(self):
        s2, e2, _ = exam_window()
        reported = make_session(s2, e2, flags=4)
        body = self.get("/summary").json()
        self.assertEqual(body["reported_ids"], [reported.id])
        self.assertEqual(body["active_count"], 2)


class BanTests(AdminBase):
    def setUp(self):
        super().setUp()
        DepartmentThreshold.objects.create(
            department=self.cse, semester="Fall 2026", min_threshold_mark=40.0, seat_limit=1, waiting_student_limit=0
        )
        self.config = AdmissionConfiguration.objects.create(
            department=self.cse, semester="Fall 2026", exam=self.exam, seat_limit=1, waiting_student_limit=0, threshold=40.0
        )

    def result_for(self, student, exam, score, **extra):
        return AdmissionResult.objects.create(
            exam=exam,
            student=student,
            department=self.cse,
            configuration=self.config,
            weighted_total_marks=score,
            attended_exam=True,
            **extra,
        )

    def test_ban_requires_reason(self):
        res = self.post("/ban", {"session_ids": [self.session.id], "reason": "  "})
        self.assertEqual(res.status_code, 400)

    def test_ban_records_who_and_why(self):
        res = self.post("/ban", {"session_ids": [self.session.id], "reason": "Phone under desk"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["banned"], [self.session.id])
        ban = ProctoringBan.objects.get()
        self.assertEqual(ban.reason, "Phone under desk")
        self.assertEqual(ban.banned_by_id, self.superadmin.id)
        self.assertTrue(ban.is_active)
        again = self.post("/ban", {"session_ids": [self.session.id], "reason": "again"})
        self.assertEqual(again.json()["already_banned"], [self.session.id])
        self.assertEqual(ProctoringBan.objects.count(), 1)

    def test_ban_mixed_selection_skips_admitted(self):
        admitted_student, _, _ = exam_window()
        assign(admitted_student, self.exam, self.schedule)
        admitted_session = make_session(admitted_student, self.exam)
        self.result_for(admitted_student, self.exam, 90.0, is_admitted=True, result_status="SELECTED", is_selected=True)
        res = self.post("/ban", {"session_ids": [self.session.id, admitted_session.id], "reason": "x"})
        body = res.json()
        self.assertEqual(body["banned"], [self.session.id])
        self.assertEqual(body["skipped_admitted"], [admitted_student.username])
        self.assertFalse(ProctoringBan.objects.filter(student=admitted_student).exists())

    def test_ban_clears_override_accept_not_admission(self):
        result = self.result_for(
            self.student, self.exam, 30.0, is_override_accepted=True, result_status="SELECTED", is_selected=True
        )
        self.post("/ban", {"session_ids": [self.session.id], "reason": "x"})
        result.refresh_from_db()
        self.assertFalse(result.is_override_accepted)
        self.assertFalse(result.is_selected)
        self.assertEqual(result.result_status, "REJECTED")

    def test_unban_restores_calculated_status(self):
        result = self.result_for(self.student, self.exam, 80.0)
        self.post("/ban", {"session_ids": [self.session.id], "reason": "x"})
        result.refresh_from_db()
        self.assertEqual(result.result_status, "REJECTED")
        res = self.post("/unban", {"session_ids": [self.session.id], "reason": "Mistake"})
        self.assertEqual(res.json()["unbanned"], [self.session.id])
        result.refresh_from_db()
        self.assertEqual(result.result_status, "SELECTED")
        ban = ProctoringBan.objects.get()
        self.assertIsNotNone(ban.lifted_at)
        self.assertEqual(ban.lift_reason, "Mistake")
        self.assertEqual(ban.lifted_by_id, self.superadmin.id)

    def test_list_marks_admitted_rows(self):
        self.result_for(self.student, self.exam, 90.0, is_admitted=True, result_status="SELECTED", is_selected=True)
        self.assertTrue(self.get("/sessions").json()["results"][0]["admitted"])


class UnlockCodeTests(AdminBase):
    def test_unlock_code_set_and_status_never_returns_code(self):
        self.assertEqual(self.get("/unlock-code").json(), {"is_set": False, "changed_at": None, "changed_by": None})
        res = self.post("/unlock-code", {"code": "lab-2027"})
        self.assertEqual(res.status_code, 200)
        body = self.get("/unlock-code").json()
        self.assertTrue(body["is_set"])
        self.assertEqual(body["changed_by"], self.superadmin.username)
        self.assertNotIn("lab-2027", str(body))
        self.assertNotIn("code_hash", body)

    def test_unlock_code_too_short_rejected(self):
        self.assertEqual(self.post("/unlock-code", {"code": "12345"}).status_code, 400)

    def test_unlock_code_needs_edit_permission(self):
        clerk = make_user("clerk3", is_global_access=True, access_type="GLOBAL")
        grant("clerk3", read=True)
        self.assertEqual(self.get("/unlock-code", user=clerk).status_code, 200)
        self.assertEqual(self.post("/unlock-code", {"code": "lab-2027"}, user=clerk).status_code, 403)
