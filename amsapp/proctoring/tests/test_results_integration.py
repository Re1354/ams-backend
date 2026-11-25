"""Bans inside AMS result calculation, Override Selection guard, and exam_conduct on results."""
import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from mainapp.models import (
    AdmissionResult,
    DepartmentThreshold,
    ExamQuestion,
    MarksDistribution,
    Submission,
)
from mainapp.services.admission_calculator import (
    apply_semester_result_statuses,
    calculate_semester_admission_results,
    recalculate_single_student_result,
)
from proctoring import services
from proctoring.models import ProctoringBan, ProctorSession

from .factories import assign, auth_header, make_department, make_exam, make_schedule, make_student, make_user

SEMESTER = "Spring 2026"
RESULTS = "/api/admission/results/"


class SemesterScenario(TestCase):
    """CSE, 2 seats, waiting list 1, threshold 40. Scores 90, 80, 70, 60, 30."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("superadmin")
        self.client.credentials(**auth_header(self.admin))
        self.cse = make_department("CSE")
        self.exam = make_exam(department="CSE", semester=SEMESTER)
        self.schedule = make_schedule(self.exam, start_offset_min=-60, end_offset_min=60)
        MarksDistribution.objects.create(department=self.cse, ssc=0, hsc=0, diploma=0, main_marks=100, viva_marks=0)
        DepartmentThreshold.objects.create(
            department=self.cse, semester=SEMESTER, min_threshold_mark=40.0, seat_limit=2, waiting_student_limit=1
        )
        self.questions = [
            ExamQuestion.objects.create(
                exam=self.exam,
                subject="Mathematics",
                question_text=f"Q{i}",
                type="option",
                options={"A": "1", "B": "2"},
                answer=json.dumps(["A"]),
                marks=10,
                semester=SEMESTER,
                department_shortname="CSE",
            )
            for i in range(10)
        ]
        self.students = {}
        for name, correct in (("s90", 9), ("s80", 8), ("s70", 7), ("s60", 6), ("s30", 3)):
            student = make_student(registration_semester=SEMESTER)
            assign(student, self.exam, self.schedule, teacher=self.admin)
            for index, question in enumerate(self.questions):
                ok = index < correct
                Submission.objects.create(
                    student=student, exam=self.exam, question=question, answer="A" if ok else "B", is_correct=ok
                )
            self.students[name] = student

    def calc(self):
        outcome = calculate_semester_admission_results(department=self.cse, semester=SEMESTER)
        self.assertTrue(outcome.get("success", True), outcome)
        return self.statuses()

    def statuses(self):
        rows = AdmissionResult.objects.filter(exam=self.exam)
        by_id = {s.id: name for name, s in self.students.items()}
        return {
            by_id[r.student_id]: (r.result_status, r.is_selected, r.department_id, r.waiting_department_id)
            for r in rows
            if r.student_id in by_id
        }

    def ban(self, name, exam=None):
        return ProctoringBan.objects.create(student=self.students[name], exam=exam or self.exam, reason="test")

    def status_of(self, name):
        return self.statuses()[name][0]


class BanCalculationTests(SemesterScenario):
    def test_baseline_without_bans(self):
        statuses = {k: v[0] for k, v in self.calc().items()}
        self.assertEqual(
            statuses, {"s90": "SELECTED", "s80": "SELECTED", "s70": "WAITING", "s60": "REJECTED", "s30": "REJECTED"}
        )

    def test_non_banned_results_identical_before_and_after(self):
        before = self.calc()
        # A ban in another semester, and a ban that was lifted, change nothing.
        other_exam = make_exam(semester="Fall 2026")
        ProctoringBan.objects.create(student=self.students["s90"], exam=other_exam, reason="other semester")
        lifted = self.ban("s80")
        lifted.lifted_at = timezone.now()
        lifted.save()
        self.assertEqual(self.calc(), before)
        apply_semester_result_statuses(
            department=self.cse, semester=SEMESTER, threshold_value=40.0, seat_limit=2, waiting_student_limit=1
        )
        self.assertEqual(self.statuses(), before)

    def test_banned_top_scorer_not_selected_next_takes_seat(self):
        self.calc()
        self.ban("s90")
        statuses = self.calc()
        self.assertEqual(statuses["s90"][:2], ("REJECTED", False))
        self.assertIsNone(statuses["s90"][3])
        self.assertEqual(
            {k: v[0] for k, v in statuses.items() if k != "s90"},
            {"s80": "SELECTED", "s70": "SELECTED", "s60": "WAITING", "s30": "REJECTED"},
        )

    def test_ban_survives_apply_statuses(self):
        self.calc()
        self.ban("s90")
        apply_semester_result_statuses(
            department=self.cse, semester=SEMESTER, threshold_value=40.0, seat_limit=2, waiting_student_limit=1
        )
        self.assertEqual(self.status_of("s90"), "REJECTED")
        self.assertEqual(self.status_of("s70"), "SELECTED")

    def test_ban_survives_single_student_recalculation(self):
        self.calc()
        self.ban("s90")
        recalculate_single_student_result(self.exam.id, self.students["s90"].id)
        self.assertEqual(self.status_of("s90"), "REJECTED")

    def test_banned_override_accepted_row_is_not_protected(self):
        self.calc()
        AdmissionResult.objects.filter(student=self.students["s60"]).update(is_override_accepted=True)
        self.ban("s60")
        apply_semester_result_statuses(
            department=self.cse, semester=SEMESTER, threshold_value=40.0, seat_limit=2, waiting_student_limit=1
        )
        self.assertEqual(self.status_of("s60"), "REJECTED")
        self.assertEqual(self.status_of("s80"), "SELECTED")

    def test_results_load_recalculation_keeps_ban(self):
        self.calc()
        self.ban("s90")
        # Window closed and a new absentee without a result row: opening Results recalculates.
        self.schedule.end_time = timezone.now() - timedelta(minutes=1)
        self.schedule.save()
        absentee = make_student(registration_semester=SEMESTER)
        assign(absentee, self.exam, self.schedule, teacher=self.admin)
        res = self.client.get(RESULTS, {"semester": SEMESTER, "department_id": self.cse.id})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(AdmissionResult.objects.filter(student=absentee).exists())
        self.assertEqual(self.status_of("s90"), "REJECTED")


class OverrideGuardTests(SemesterScenario):
    def bulk(self, names, **body):
        ids = [self.students[n].id for n in names]
        return self.client.post(
            f"{RESULTS}bulk-status-update/", {"student_ids": ids, "exam_id": self.exam.id, **body}, format="json"
        )

    def test_override_selection_refuses_banned(self):
        self.calc()
        self.ban("s90")
        self.calc()
        res = self.bulk(["s90", "s30"], action="SET_STATUS", result_status="SELECTED")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["message"], "This student is banned in Proctoring. Unban first.")
        self.assertEqual(res.json()["banned_candidates"], [self.students["s90"].username])
        self.assertEqual(self.status_of("s30"), "REJECTED")

    def test_override_still_works_for_others(self):
        self.calc()
        self.ban("s90")
        self.calc()
        res = self.bulk(["s60"], action="SET_STATUS", result_status="SELECTED")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.status_of("s60"), "SELECTED")

    def test_mark_not_selected_works_with_a_banned_student_in_the_selection(self):
        self.calc()
        self.ban("s90")
        self.calc()
        res = self.bulk(["s90", "s60"], action="SET_STATUS", result_status="REJECTED")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.status_of("s90"), "REJECTED")
        self.assertEqual(self.status_of("s60"), "REJECTED")

    def test_revert_keeps_a_banned_student_not_selected(self):
        self.calc()
        self.ban("s90")
        self.calc()
        res = self.bulk(["s90"], action="REVERT_TO_STORED_STATUS")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.status_of("s90"), "REJECTED")

    def test_waiting_refused_for_banned(self):
        self.calc()
        self.ban("s90")
        self.calc()
        res = self.bulk(["s90"], action="SET_STATUS", result_status="WAITING")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.status_of("s90"), "REJECTED")

    def test_admit_refused_for_banned(self):
        self.calc()
        self.ban("s90")
        self.calc()
        res = self.bulk(["s90"], action="SET_ADMITTED")
        self.assertEqual(res.status_code, 400)
        self.assertFalse(AdmissionResult.objects.get(student=self.students["s90"]).is_admitted)


class ExamConductFieldTests(SemesterScenario):
    def session(self, name, flags):
        session = ProctorSession.objects.create(
            student=self.students[name], exam=self.exam, token=services.secrets.token_hex(20)
        )
        for _ in range(flags):
            services.record_flag(session, "TAB_SWITCH", {}, None, None)
        return session

    def conduct_rows(self):
        res = self.client.get(RESULTS, {"semester": SEMESTER, "department_id": self.cse.id, "page_size": 50})
        self.assertEqual(res.status_code, 200)
        rows = res.json()["results"]
        by_id = {s.id: name for name, s in self.students.items()}
        return {by_id[r["student"]]: r["exam_conduct"] for r in rows if r.get("student") in by_id}

    def test_results_api_includes_exam_conduct(self):
        self.calc()
        clear = self.session("s80", 1)
        reported = self.session("s70", 4)
        self.ban("s90")
        rows = self.conduct_rows()
        self.assertEqual(rows["s90"]["status"], "banned")
        self.assertEqual(rows["s80"], {"status": "clear", "flag_count": 1, "session_id": clear.id})
        self.assertEqual(rows["s70"], {"status": "reported", "flag_count": 4, "session_id": reported.id})

    def test_conduct_not_monitored_without_session(self):
        self.calc()
        rows = self.conduct_rows()
        self.assertEqual(rows["s60"], {"status": "not_monitored", "flag_count": 0, "session_id": None})

    def test_conduct_reported_after_more_than_three_counted_flags(self):
        self.calc()
        self.session("s80", 3)
        self.assertEqual(self.conduct_rows()["s80"]["status"], "clear")
        services.record_flag(ProctorSession.objects.get(student=self.students["s80"]), "TAB_SWITCH", {}, None, None)
        self.assertEqual(self.conduct_rows()["s80"]["status"], "reported")
