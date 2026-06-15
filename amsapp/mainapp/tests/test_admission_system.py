import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    AdmissionResult,
    Department,
    DepartmentThreshold,
    Exam,
    ExamQuestion,
    ExamSchedule,
    MarksDistribution,
    Role,
    StudentAssignTeacherExam,
    Students,
    Submission,
    User,
    VivaAssignment,
    VivaRubrics,
)
from ..models.viva_marks import VivaMarks
from ..tokens import get_tokens_for_user
from ..services.admission_calculator import calculate_weighted_scores
from ..views.admission_report import (
    build_student_admission_pdf_context,
    render_student_admission_report_pdf_html,
    resolve_report_faculty_name,
)


class AdmissionSystemTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]

        self.admin_role = Role.objects.create(role_name=f"Admin-{suffix}")
        self.dept_cse = Department.objects.create(
            department_name=f"Computer Science & Engineering {suffix}",
            department_shortname="CSE",
        )
        self.dept_eee = Department.objects.create(
            department_name=f"Electrical & Electronic Engineering {suffix}",
            department_shortname="EEE",
        )
        self.admin_user = User.objects.create(
            username=f"admin-{suffix}",
            email=f"admin-{suffix}@test.com",
            password=make_password("admin123"),
            role=self.admin_role,
            department=self.dept_cse,
        )
        self.second_teacher = User.objects.create(
            username=f"teacher2-{suffix}",
            email=f"teacher2-{suffix}@test.com",
            password=make_password("admin123"),
            role=self.admin_role,
            department=self.dept_cse,
        )

        tokens = get_tokens_for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        self.exam = Exam.objects.create(
            department="CSE",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )
        self.schedule = ExamSchedule.objects.create(
            exam=self.exam,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            is_active=True,
        )
        self.student1 = Students.objects.create(
            username=f"student1-{suffix}",
            password="pass123",
            f_id=f"F001-{suffix}",
            full_name="Student One",
            email=f"student1-{suffix}@test.com",
            department_shortname="CSE",
            registration_semester="Spring 2026",
            ssc=90,
            hsc=95,
        )
        self.student2 = Students.objects.create(
            username=f"student2-{suffix}",
            password="pass123",
            f_id=f"F002-{suffix}",
            full_name="Student Two",
            email=f"student2-{suffix}@test.com",
            department_shortname="CSE",
            registration_semester="Spring 2026",
            ssc=80,
            hsc=85,
        )
        self.student3 = Students.objects.create(
            username=f"student3-{suffix}",
            password="pass123",
            f_id=f"F003-{suffix}",
            full_name="Student Three",
            email=f"student3-{suffix}@test.com",
            department_shortname="EEE",
            registration_semester="Spring 2026",
            ssc=88,
            hsc=89,
        )

        for student in (self.student1, self.student2, self.student3):
            StudentAssignTeacherExam.objects.create(
                student=student,
                teacher=self.admin_user,
                exam=self.exam,
                schedule=self.schedule,
            )

        MarksDistribution.objects.create(
            department=self.dept_cse,
            ssc=0,
            hsc=0,
            diploma=0,
            main_marks=100,
            viva_marks=0,
        )
        MarksDistribution.objects.create(
            department=self.dept_eee,
            ssc=0,
            hsc=0,
            diploma=0,
            main_marks=100,
            viva_marks=0,
        )

        self.questions = []
        for index in range(10):
            self.questions.append(
                ExamQuestion.objects.create(
                    exam=self.exam,
                    subject="Mathematics",
                    question_text=f"Question {index + 1}",
                    type="option",
                    options={"A": "1", "B": "2", "C": "3", "D": "4"},
                    answer=json.dumps(["A"]),
                    marks=10,
                    semester="Spring 2026",
                    department_shortname="CSE",
                )
            )

    def create_submissions_for_student(self, student, correct_count):
        for index, question in enumerate(self.questions):
            is_correct = index < correct_count
            Submission.objects.create(
                student=student,
                exam=self.exam,
                question=question,
                answer="A" if is_correct else "B",
                is_correct=is_correct,
            )

    def create_assigned_student(self, index, department_shortname="CSE"):
        suffix = uuid4().hex[:8]
        student = Students.objects.create(
            username=f"candidate-{index}-{suffix}",
            password="pass123",
            f_id=f"FC-{index:03d}-{suffix}",
            full_name=f"Candidate {index}",
            email=f"candidate-{index}-{suffix}@test.com",
            department_shortname=department_shortname,
            registration_semester="Spring 2026",
            ssc=80,
            hsc=80,
        )
        StudentAssignTeacherExam.objects.create(
            student=student,
            teacher=self.admin_user,
            exam=self.exam,
            schedule=self.schedule,
        )
        return student

    def set_thresholds(
        self,
        cse_threshold=60.0,
        eee_threshold=70.0,
        cse_seat_limit=10,
        eee_seat_limit=10,
        cse_waiting_student_limit=0,
        eee_waiting_student_limit=0,
    ):
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            semester=self.exam.semester,
            min_threshold_mark=cse_threshold,
            seat_limit=cse_seat_limit,
            waiting_student_limit=cse_waiting_student_limit,
        )
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_eee,
            semester=self.exam.semester,
            min_threshold_mark=eee_threshold,
            seat_limit=eee_seat_limit,
            waiting_student_limit=eee_waiting_student_limit,
        )

    def test_set_threshold_mapping_success(self):
        response = self.client.post(
            "/api/admission/threshold-mapping/",
            {
                "semester": self.exam.semester,
                "mappings": [
                    {
                        "department_id": self.dept_cse.id,
                        "threshold": 60.0,
                        "seat_limit": 5,
                        "waiting_student_limit": 2,
                    },
                    {
                        "department_id": self.dept_eee.id,
                        "threshold": 75.0,
                        "seat_limit": 8,
                        "waiting_student_limit": 3,
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["created_count"], 2)
        self.assertEqual(
            DepartmentThreshold.objects.filter(semester=self.exam.semester).count(),
            2,
        )
        cse_threshold = DepartmentThreshold.objects.get(
            semester=self.exam.semester,
            department=self.dept_cse,
        )
        self.assertEqual(cse_threshold.waiting_student_limit, 2)

    def test_calculate_results_creates_waiting_rejected_and_absent_statuses(self):
        self.set_thresholds(cse_threshold=60.0, eee_threshold=70.0)
        self.create_submissions_for_student(self.student1, correct_count=7)  # 70
        self.create_submissions_for_student(self.student2, correct_count=5)  # 50
        VivaMarks.objects.create(student=self.student1, marks=0, rubrics_marks={})

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["processed_count"], 3)
        self.assertEqual(response.data["status_counts"]["SELECTED"], 1)
        self.assertEqual(response.data["status_counts"]["REJECTED"], 1)
        self.assertEqual(response.data["status_counts"]["ABSENT"], 1)

        result1 = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        result2 = AdmissionResult.objects.get(student=self.student2, exam=self.exam)
        result3 = AdmissionResult.objects.get(student=self.student3, exam=self.exam)

        self.assertEqual(result1.weighted_total_marks, 70.0)
        self.assertEqual(result1.result_status, "SELECTED")
        self.assertTrue(result1.is_selected)

        self.assertEqual(result2.weighted_total_marks, 50.0)
        self.assertEqual(result2.result_status, "REJECTED")
        self.assertFalse(result2.is_selected)

        self.assertEqual(result3.result_status, "ABSENT")
        self.assertFalse(result3.attended_exam)
        self.assertFalse(result3.is_selected)

    def test_seat_limit_marks_extra_qualifying_students_waiting_not_selected(self):
        self.set_thresholds(
            cse_threshold=90.0,
            eee_threshold=70.0,
            cse_seat_limit=1,
            cse_waiting_student_limit=1,
        )
        self.create_submissions_for_student(self.student1, correct_count=10)  # 100
        self.create_submissions_for_student(self.student2, correct_count=9)  # 90

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status_counts"]["SELECTED"], 1)
        self.assertEqual(response.data["status_counts"]["WAITING"], 1)

        selected_result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        waiting_result = AdmissionResult.objects.get(student=self.student2, exam=self.exam)

        self.assertEqual(selected_result.result_status, "SELECTED")
        self.assertTrue(selected_result.is_selected)
        self.assertFalse(selected_result.is_override_accepted)

        self.assertEqual(waiting_result.result_status, "WAITING")
        self.assertFalse(waiting_result.is_selected)
        self.assertFalse(waiting_result.is_override_accepted)

    def test_zero_waiting_limit_marks_extra_attended_candidates_rejected(self):
        self.set_thresholds(cse_threshold=90.0, eee_threshold=70.0, cse_seat_limit=1)
        self.create_submissions_for_student(self.student1, correct_count=10)  # 100
        self.create_submissions_for_student(self.student2, correct_count=9)  # 90

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status_counts"]["SELECTED"], 1)
        self.assertEqual(response.data["status_counts"]["WAITING"], 0)
        self.assertEqual(response.data["status_counts"]["REJECTED"], 1)

        selected_result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        rejected_result = AdmissionResult.objects.get(student=self.student2, exam=self.exam)

        self.assertEqual(selected_result.result_status, "SELECTED")
        self.assertEqual(rejected_result.result_status, "REJECTED")
        self.assertFalse(rejected_result.is_selected)

    def test_bulk_assignment_uses_schedule_for_duplicate_detection(self):
        second_schedule = ExamSchedule.objects.create(
            exam=self.exam,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            is_active=True,
        )

        response = self.client.post(
            "/api/student-assignments/assign-bulk/",
            {
                "student_ids": [self.student1.id],
                "teacher_id": self.admin_user.id,
                "schedule_id": second_schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["created_count"], 1)
        self.assertTrue(
            StudentAssignTeacherExam.objects.filter(
                student=self.student1,
                teacher=self.admin_user,
                exam=self.exam,
                schedule=second_schedule,
            ).exists()
        )

    def test_waiting_limit_takes_next_best_attended_candidates(self):
        self.set_thresholds(
            cse_threshold=90.0,
            eee_threshold=70.0,
            cse_seat_limit=1,
            cse_waiting_student_limit=2,
        )
        extra_student = self.create_assigned_student(99)
        self.create_submissions_for_student(self.student1, correct_count=10)  # 100
        self.create_submissions_for_student(self.student2, correct_count=8)  # 80
        self.create_submissions_for_student(extra_student, correct_count=7)  # 70

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status_counts"]["SELECTED"], 1)
        self.assertEqual(response.data["status_counts"]["WAITING"], 2)

        self.assertEqual(
            AdmissionResult.objects.get(student=self.student2, exam=self.exam).result_status,
            "WAITING",
        )
        self.assertEqual(
            AdmissionResult.objects.get(student=extra_student, exam=self.exam).result_status,
            "WAITING",
        )

    def test_missing_configuration_does_not_create_admission_results(self):
        self.create_submissions_for_student(self.student1, correct_count=7)

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["configuration_missing"])
        self.assertFalse(AdmissionResult.objects.filter(exam=self.exam).exists())

    def test_zero_seat_limit_is_treated_as_missing_configuration(self):
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            semester=self.exam.semester,
            min_threshold_mark=40.0,
            seat_limit=0,
        )
        self.create_submissions_for_student(self.student1, correct_count=7)

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["configuration_missing"])
        self.assertFalse(AdmissionResult.objects.filter(exam=self.exam).exists())

    def test_override_accept_displaces_last_natural_candidate_and_removal_restores(self):
        self.set_thresholds(
            cse_threshold=40.0,
            eee_threshold=40.0,
            cse_seat_limit=50,
            cse_waiting_student_limit=1,
        )
        candidates = []
        for index in range(51):
            candidate = self.create_assigned_student(index)
            candidates.append(candidate)
            self.create_submissions_for_student(candidate, correct_count=4)

        response = self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        candidate_ids = [candidate.id for candidate in candidates]
        self.assertEqual(
            AdmissionResult.objects.filter(
                exam=self.exam,
                student_id__in=candidate_ids,
                result_status="SELECTED",
            ).count(),
            50,
        )

        displaced_result = AdmissionResult.objects.get(exam=self.exam, student=candidates[-2])
        override_result = AdmissionResult.objects.get(exam=self.exam, student=candidates[-1])
        self.assertEqual(displaced_result.result_status, "SELECTED")
        self.assertEqual(override_result.result_status, "WAITING")

        override_response = self.client.post(
            "/api/admission/results/bulk-status-update/",
            {
                "configuration_id": override_result.configuration_id,
                "student_ids": [override_result.student_id],
                "result_status": "SELECTED",
            },
            format="json",
        )
        self.assertEqual(override_response.status_code, status.HTTP_200_OK)

        displaced_result.refresh_from_db()
        override_result.refresh_from_db()
        self.assertEqual(displaced_result.result_status, "WAITING")
        self.assertFalse(displaced_result.is_selected)
        self.assertEqual(override_result.result_status, "SELECTED")
        self.assertTrue(override_result.is_selected)
        self.assertTrue(override_result.is_override_accepted)
        self.assertEqual(
            AdmissionResult.objects.filter(
                exam=self.exam,
                student_id__in=candidate_ids,
                result_status="SELECTED",
            ).count(),
            50,
        )

        revert_response = self.client.post(
            "/api/admission/results/bulk-status-update/",
            {
                "configuration_id": override_result.configuration_id,
                "student_ids": [override_result.student_id],
                "action": "REVERT_TO_STORED_STATUS",
            },
            format="json",
        )
        self.assertEqual(revert_response.status_code, status.HTTP_200_OK)

        displaced_result.refresh_from_db()
        override_result.refresh_from_db()
        self.assertEqual(displaced_result.result_status, "SELECTED")
        self.assertTrue(displaced_result.is_selected)
        self.assertEqual(override_result.result_status, "WAITING")
        self.assertFalse(override_result.is_selected)
        self.assertFalse(override_result.is_override_accepted)

    def test_submit_exam_triggers_admission_recalculation_when_configured(self):
        self.set_thresholds(cse_threshold=10.0, eee_threshold=10.0)

        response = self.client.post(
            f"/api/student/exam/{self.exam.id}/submit/",
            {
                "student_id": self.student1.id,
                "submissions": [{"question_id": self.questions[0].id, "answer": "A"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_submitted"], 1)
        self.assertTrue(response.data["admission_recalculation"]["attempted"])
        self.assertTrue(response.data["admission_recalculation"]["success"])
        self.assertFalse(response.data["admission_recalculation"]["configuration_missing"])

        result = AdmissionResult.objects.get(exam=self.exam, student=self.student1)
        self.assertEqual(result.weighted_total_marks, 10.0)
        self.assertEqual(result.result_status, "SELECTED")

    def test_submit_exam_skips_admission_recalculation_when_configuration_missing(self):
        response = self.client.post(
            f"/api/student/exam/{self.exam.id}/submit/",
            {
                "student_id": self.student1.id,
                "submissions": [{"question_id": self.questions[0].id, "answer": "A"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["admission_recalculation"]["attempted"])
        self.assertTrue(response.data["admission_recalculation"]["configuration_missing"])
        self.assertFalse(AdmissionResult.objects.filter(exam=self.exam).exists())

    def test_get_admission_results_filters_by_result_status_and_semester(self):
        self.set_thresholds()
        self.create_submissions_for_student(self.student1, correct_count=7)
        self.create_submissions_for_student(self.student2, correct_count=5)
        self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        response = self.client.get(
            f"/api/admission/results/?department_id={self.dept_cse.id}&semester=Spring 2026&result_status=SELECTED"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["student_username"],
            self.student1.username,
        )
        self.assertEqual(response.data["configuration"]["semester"], "Spring 2026")

    def test_publish_and_recalculate_student_result(self):
        self.set_thresholds()
        self.create_submissions_for_student(self.student1, correct_count=6)
        self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        publish_response = self.client.post(
            "/api/admission/publish-results/",
            {"exam_id": self.exam.id},
            format="json",
        )
        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            AdmissionResult.objects.get(student=self.student1, exam=self.exam).status,
            "PUBLISHED",
        )

        submission = Submission.objects.get(student=self.student1, exam=self.exam, question=self.questions[6])
        submission.answer = "A"
        submission.is_correct = True
        submission.save(update_fields=["answer", "is_correct"])

        recalculate_response = self.client.post(
            f"/api/admission/recalculate/{self.exam.id}/{self.student1.id}/",
            format="json",
        )
        self.assertEqual(recalculate_response.status_code, status.HTTP_200_OK)
        refreshed = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(refreshed.weighted_total_marks, 70.0)
        self.assertEqual(refreshed.result_status, "SELECTED")

    def test_student_detail_report_returns_written_viva_and_snapshot_data(self):
        self.set_thresholds(cse_threshold=10.0, eee_threshold=10.0)

        Submission.objects.create(
            student=self.student1,
            exam=self.exam,
            question=self.questions[0],
            answer="A",
            is_correct=True,
        )
        Submission.objects.create(
            student=self.student1,
            exam=self.exam,
            question=self.questions[1],
            answer="B",
            is_correct=False,
        )
        Submission.objects.create(
            student=self.student1,
            exam=self.exam,
            question=self.questions[2],
            answer="A",
            is_correct=True,
        )

        rubric_one = VivaRubrics.objects.create(
            department=self.dept_cse,
            rubrics="Communication",
            marks=5,
        )
        rubric_two = VivaRubrics.objects.create(
            department=self.dept_cse,
            rubrics="Subject Knowledge",
            marks=5,
        )
        VivaAssignment.objects.filter(student=self.student1, exam=self.exam).delete()
        VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now() + timedelta(days=1),
            time=(timezone.now() + timedelta(days=1)).time(),
            room="Room 202",
            total_marks=7.5,
            rubric_snapshot=[
                {"source_rubric_id": rubric_one.id, "criteria": "Communication", "max_marks": 5.0},
                {"source_rubric_id": rubric_two.id, "criteria": "Subject Knowledge", "max_marks": 5.0},
            ],
            rubric_scores={str(rubric_one.id): 4, str(rubric_two.id): 3.5},
            remarks="Strong viva performance",
        )

        self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        rubric_one.rubrics = "Changed Rubric Text"
        rubric_one.save(update_fields=["rubrics"])

        response = self.client.get(
            f"/api/admission/reports/student/{self.exam.id}/{self.student1.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])

        report = response.data["data"]
        self.assertEqual(report["student"]["application_serial"], self.student1.f_id)
        self.assertEqual(report["written_exam"]["assigned_teacher"], self.admin_user.username)
        self.assertEqual(report["written_summary"]["correct_answers"], 2)
        self.assertEqual(report["written_summary"]["wrong_answers"], 1)
        self.assertEqual(report["written_summary"]["skipped_answers"], 7)
        self.assertEqual(len(report["question_reviews"]), 10)
        self.assertEqual(report["question_reviews"][0]["status"], "CORRECT")
        self.assertEqual(report["question_reviews"][1]["status"], "WRONG")
        self.assertEqual(report["question_reviews"][3]["status"], "SKIPPED")
        self.assertEqual(report["viva"]["rubric_rows"][0]["criteria"], "Communication")
        self.assertEqual(report["viva"]["total_marks"], 7.5)
        self.assertEqual(report["final_result"]["result_status"], "SELECTED")

    def test_student_detail_report_pdf_html_includes_rubrics_equations_and_pdf_response(self):
        self.set_thresholds(cse_threshold=10.0, eee_threshold=10.0)

        Submission.objects.create(
            student=self.student1,
            exam=self.exam,
            question=self.questions[0],
            answer="A",
            is_correct=True,
        )
        Submission.objects.create(
            student=self.student1,
            exam=self.exam,
            question=self.questions[1],
            answer="B",
            is_correct=False,
        )

        rubric_one = VivaRubrics.objects.create(
            department=self.dept_cse,
            rubrics="Communication",
            marks=5,
        )
        rubric_two = VivaRubrics.objects.create(
            department=self.dept_cse,
            rubrics="Subject Knowledge",
            marks=5,
        )
        VivaAssignment.objects.filter(student=self.student1, exam=self.exam).delete()
        VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now() + timedelta(days=1),
            time=(timezone.now() + timedelta(days=1)).time(),
            room="Room 101",
            total_marks=6.5,
            rubric_snapshot=[
                {"source_rubric_id": rubric_one.id, "criteria": "Communication", "max_marks": 5.0},
                {"source_rubric_id": rubric_two.id, "criteria": "Subject Knowledge", "max_marks": 5.0},
            ],
            rubric_scores={str(rubric_one.id): 3.5, str(rubric_two.id): 3},
            remarks="Balanced viva performance",
        )

        self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )

        report_response = self.client.get(
            f"/api/admission/reports/student/{self.exam.id}/{self.student1.id}/"
        )
        self.assertEqual(report_response.status_code, status.HTTP_200_OK)
        report = report_response.data["data"]

        context = build_student_admission_pdf_context(report)
        self.assertEqual(context["faculty_name"], "Science and Information Technology")
        self.assertTrue(context["calculation_equations"])

        html = render_student_admission_report_pdf_html(report)
        self.assertIn("Viva Rubric Breakdown", html)
        self.assertIn("Communication", html)
        self.assertIn("Weighted Total Equation", html)
        self.assertIn("SSC Contribution =", html)
        self.assertIn("SSC Score / SSC Total", html)
        self.assertIn("Written Marks / Total Written Marks", html)
        self.assertIn("Daffodil International University", html)

        pdf_response = self.client.get(
            f"/api/admission/reports/student/{self.exam.id}/{self.student1.id}/pdf/",
            HTTP_ACCEPT="application/pdf",
        )
        if pdf_response.status_code == status.HTTP_200_OK:
            self.assertEqual(pdf_response["Content-Type"], "application/pdf")
            self.assertIn(".pdf", pdf_response["Content-Disposition"])
            self.assertTrue(bytes(pdf_response.content).startswith(b"%PDF"))
        else:
            self.assertEqual(pdf_response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertEqual(pdf_response["Content-Type"], "application/json")
            self.assertIn("PDF renderer is unavailable", str(pdf_response.json().get("message")))

    def test_resolve_report_faculty_name_uses_department_mapping(self):
        faculty_name = resolve_report_faculty_name(
            {
                "student": {"department_shortname": "EEE"},
                "written_exam": {"faculty": "", "department": "EEE"},
            }
        )

        self.assertEqual(faculty_name, "Engineering")

    def test_calculate_weighted_scores_uses_gpa_scale_and_actual_written_viva_totals(self):
        cse_distribution = MarksDistribution.objects.get(department=self.dept_cse)
        cse_distribution.ssc = 5
        cse_distribution.hsc = 5
        cse_distribution.diploma = 5
        cse_distribution.main_marks = 80
        cse_distribution.viva_marks = 10
        cse_distribution.save()

        self.student1.ssc = 5.0
        self.student1.hsc = 4.5
        self.student1.save(update_fields=["ssc", "hsc"])

        self.exam.total_marks = 999
        self.exam.save(update_fields=["total_marks"])

        VivaAssignment.objects.filter(student=self.student1, exam=self.exam).delete()
        VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now() + timedelta(days=1),
            time=(timezone.now() + timedelta(days=1)).time(),
            room="Room 303",
            total_marks=16.5,
            rubric_snapshot=[
                {"source_rubric_id": 1, "criteria": "Communication", "max_marks": 10.0},
                {"source_rubric_id": 2, "criteria": "Subject Knowledge", "max_marks": 10.0},
            ],
            rubric_scores={"1": 8.0, "2": 8.5},
            remarks="Strong viva",
        )

        weighted = calculate_weighted_scores(
            student=self.student1,
            exam=self.exam,
            department=self.dept_cse,
            mcq_marks=32,
            viva_marks=16.5,
        )

        self.assertEqual(weighted["written_total_marks"], 100.0)
        self.assertEqual(weighted["viva_total_marks"], 20.0)
        self.assertEqual(weighted["ssc_contribution"], 5.0)
        self.assertEqual(weighted["academic_contribution"], 4.5)
        self.assertEqual(weighted["written_contribution"], 25.6)
        self.assertEqual(weighted["viva_contribution"], 8.25)
        self.assertEqual(weighted["weighted_total_marks"], 43.35)

    def test_calculate_weighted_scores_uses_diploma_out_of_four(self):
        cse_distribution = MarksDistribution.objects.get(department=self.dept_cse)
        cse_distribution.ssc = 5
        cse_distribution.hsc = 5
        cse_distribution.diploma = 10
        cse_distribution.main_marks = 80
        cse_distribution.viva_marks = 0
        cse_distribution.save()

        self.student1.ssc = 4.5
        self.student1.hsc = 0
        self.student1.diploma = 3.2
        self.student1.save(update_fields=["ssc", "hsc", "diploma"])

        weighted = calculate_weighted_scores(
            student=self.student1,
            exam=self.exam,
            department=self.dept_cse,
            mcq_marks=50,
            viva_marks=0,
        )

        self.assertEqual(weighted["ssc_contribution"], 4.5)
        self.assertEqual(weighted["academic_contribution"], 8.0)
        self.assertEqual(weighted["written_contribution"], 40.0)
        self.assertEqual(weighted["viva_contribution"], 0.0)
        self.assertEqual(weighted["weighted_total_marks"], 52.5)

    def test_teacher_results_and_viva_updates_use_teacher_specific_assignment(self):
        StudentAssignTeacherExam.objects.create(
            student=self.student1,
            teacher=self.second_teacher,
            exam=self.exam,
            schedule=self.schedule,
        )
        VivaAssignment.objects.filter(student=self.student1, exam=self.exam).delete()
        primary_assignment = VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now() + timedelta(days=1),
            time=(timezone.now() + timedelta(days=1)).time(),
            room="Room 101",
            total_marks=0,
            rubric_snapshot=[
                {"source_rubric_id": 1, "criteria": "Communication", "max_marks": 5.0},
                {"source_rubric_id": 2, "criteria": "Knowledge", "max_marks": 5.0},
            ],
            rubric_scores={},
            remarks="",
        )
        secondary_assignment = VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.second_teacher,
            exam=self.exam,
            scheduled_at=timezone.now() + timedelta(days=1),
            time=(timezone.now() + timedelta(days=1)).time(),
            room="Room 102",
            total_marks=2,
            rubric_snapshot=[
                {"source_rubric_id": 3, "criteria": "Communication", "max_marks": 5.0},
                {"source_rubric_id": 4, "criteria": "Knowledge", "max_marks": 5.0},
            ],
            rubric_scores={"3": 1, "4": 1},
            remarks="Older marks",
        )
        VivaMarks.objects.create(
            student=self.student1,
            marks=0,
            rubrics_marks={},
            remarks="",
        )

        Submission.objects.create(
            student=self.student1,
            exam=self.exam,
            question=self.questions[0],
            answer="A",
            is_correct=True,
        )

        primary_tokens = get_tokens_for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {primary_tokens['access']}")
        update_response = self.client.post(
            f"/api/add-viva-marks/{self.student1.id}/",
            {
                "exam_id": self.exam.id,
                "marks": 8,
                "rubrics_marks": {"1": 4, "2": 4},
                "remarks": "Updated by primary teacher",
            },
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        primary_assignment.refresh_from_db()
        secondary_assignment.refresh_from_db()
        self.assertEqual(primary_assignment.total_marks, 8)
        self.assertEqual(primary_assignment.rubric_scores, {"1": 4, "2": 4})
        self.assertEqual(primary_assignment.remarks, "Updated by primary teacher")
        self.assertEqual(secondary_assignment.total_marks, 2)
        self.assertEqual(secondary_assignment.rubric_scores, {"3": 1, "4": 1})

        teacher_one_results = self.client.get(
            f"/api/get-all-results-by-teacher/{self.admin_user.id}/"
        )
        self.assertEqual(teacher_one_results.status_code, status.HTTP_200_OK)
        self.assertEqual(
            teacher_one_results.data["data"]["results"][0]["viva_marks"]["marks"],
            8,
        )
        self.assertEqual(
            teacher_one_results.data["data"]["results"][0]["viva_marks"]["remarks"],
            "Updated by primary teacher",
        )

        second_tokens = get_tokens_for_user(self.second_teacher)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {second_tokens['access']}")
        teacher_two_results = self.client.get(
            f"/api/get-all-results-by-teacher/{self.second_teacher.id}/"
        )
        self.assertEqual(teacher_two_results.status_code, status.HTTP_200_OK)
        self.assertEqual(
            teacher_two_results.data["data"]["results"][0]["viva_marks"]["marks"],
            2,
        )
        self.assertEqual(
            teacher_two_results.data["data"]["results"][0]["viva_marks"]["remarks"],
            "Older marks",
        )

    def test_teacher_results_endpoint_returns_paginated_page(self):
        self.create_submissions_for_student(self.student1, correct_count=6)
        self.create_submissions_for_student(self.student2, correct_count=5)

        VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now(),
            time=timezone.now().time(),
            total_marks=7,
            rubric_scores={"1": 4, "2": 3},
            remarks="First paginated viva",
        )
        VivaAssignment.objects.create(
            student=self.student2,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now(),
            time=timezone.now().time(),
            total_marks=8,
            rubric_scores={"1": 4, "2": 4},
            remarks="Second paginated viva",
        )

        response = self.client.get(
            f"/api/get-all-results-by-teacher/{self.admin_user.id}/?page_size=1&page=2"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        pagination = response.data["data"]["pagination"]
        self.assertEqual(pagination["count"], 2)
        self.assertEqual(pagination["total_pages"], 2)
        self.assertEqual(pagination["current_page"], 2)
        self.assertEqual(pagination["page_size"], 1)
        self.assertEqual(len(response.data["data"]["results"]), 1)

    def test_add_viva_marks_recalculates_admission_result_immediately(self):
        self.set_thresholds(cse_threshold=55.0, eee_threshold=70.0)
        MarksDistribution.objects.filter(department=self.dept_cse).update(
            ssc=0,
            hsc=0,
            diploma=0,
            main_marks=80,
            viva_marks=20,
        )
        self.create_submissions_for_student(self.student1, correct_count=6)

        primary_assignment = VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now(),
            time=timezone.now().time(),
            room="Room 101",
            total_marks=0,
            rubric_snapshot=[
                {"source_rubric_id": 1, "criteria": "Communication", "max_marks": 10.0},
                {"source_rubric_id": 2, "criteria": "Knowledge", "max_marks": 10.0},
            ],
            rubric_scores={},
            remarks="",
        )
        VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.second_teacher,
            exam=self.exam,
            scheduled_at=timezone.now() + timedelta(hours=1),
            time=(timezone.now() + timedelta(hours=1)).time(),
            room="Room 102",
            total_marks=0,
            rubric_snapshot=[
                {"source_rubric_id": 3, "criteria": "Communication", "max_marks": 10.0},
                {"source_rubric_id": 4, "criteria": "Knowledge", "max_marks": 10.0},
            ],
            rubric_scores={},
            remarks="",
        )

        self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )
        initial_result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(initial_result.weighted_total_marks, 48.0)
        self.assertEqual(initial_result.viva_marks, 0.0)
        self.assertEqual(initial_result.result_status, "REJECTED")

        response = self.client.post(
            f"/api/add-viva-marks/{self.student1.id}/",
            {
                "exam_id": self.exam.id,
                "marks": 10,
                "rubrics_marks": {"1": 5, "2": 5},
                "remarks": "Strong viva",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["recalculated_result"]["exam_id"], self.exam.id)
        self.assertEqual(response.data["recalculated_result"]["student_id"], self.student1.id)
        self.assertEqual(response.data["recalculated_result"]["viva_marks"], 10.0)
        self.assertEqual(response.data["recalculated_result"]["weighted_total_marks"], 58.0)
        self.assertEqual(response.data["recalculated_result"]["result_status"], "SELECTED")
        self.assertTrue(response.data["recalculated_result"]["is_selected"])

        primary_assignment.refresh_from_db()
        self.assertEqual(primary_assignment.total_marks, 10)
        self.assertEqual(primary_assignment.rubric_scores, {"1": 5, "2": 5})

        refreshed_result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(refreshed_result.viva_marks, 10.0)
        self.assertEqual(refreshed_result.viva_contribution, 10.0)
        self.assertEqual(refreshed_result.weighted_total_marks, 58.0)
        self.assertEqual(refreshed_result.result_status, "SELECTED")
        self.assertTrue(refreshed_result.is_selected)

    def test_delete_viva_marks_recalculates_admission_result_downward(self):
        self.set_thresholds(cse_threshold=55.0, eee_threshold=70.0)
        MarksDistribution.objects.filter(department=self.dept_cse).update(
            ssc=0,
            hsc=0,
            diploma=0,
            main_marks=80,
            viva_marks=20,
        )
        self.create_submissions_for_student(self.student1, correct_count=6)

        viva_assignment = VivaAssignment.objects.create(
            student=self.student1,
            teacher=self.admin_user,
            exam=self.exam,
            scheduled_at=timezone.now(),
            time=timezone.now().time(),
            room="Room 101",
            total_marks=10,
            rubric_snapshot=[
                {"source_rubric_id": 1, "criteria": "Communication", "max_marks": 10.0},
                {"source_rubric_id": 2, "criteria": "Knowledge", "max_marks": 10.0},
            ],
            rubric_scores={"1": 5, "2": 5},
            remarks="Strong viva",
        )
        VivaMarks.objects.create(
            student=self.student1,
            marks=10,
            rubrics_marks={"1": 5, "2": 5},
            remarks="Strong viva",
        )

        self.client.post(
            "/api/admission/calculate-results/",
            {"exam_id": self.exam.id},
            format="json",
        )
        initial_result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(initial_result.weighted_total_marks, 58.0)
        self.assertEqual(initial_result.result_status, "SELECTED")

        response = self.client.delete(
            f"/api/delete-viva-marks/{self.student1.id}/?exam_id={self.exam.id}",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["recalculated_result"]["viva_marks"], 0.0)
        self.assertEqual(response.data["recalculated_result"]["weighted_total_marks"], 48.0)
        self.assertEqual(response.data["recalculated_result"]["result_status"], "REJECTED")
        self.assertFalse(response.data["recalculated_result"]["is_selected"])

        viva_assignment.refresh_from_db()
        self.assertEqual(viva_assignment.total_marks, 0.0)
        self.assertEqual(viva_assignment.rubric_scores, {})
        self.assertIsNone(viva_assignment.remarks)
        self.assertFalse(VivaMarks.objects.filter(student=self.student1).exists())

        refreshed_result = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        self.assertEqual(refreshed_result.viva_marks, 0.0)
        self.assertEqual(refreshed_result.viva_contribution, 0.0)
        self.assertEqual(refreshed_result.weighted_total_marks, 48.0)
        self.assertEqual(refreshed_result.result_status, "REJECTED")
        self.assertFalse(refreshed_result.is_selected)


class TokenHelperCompatibilityTests(TestCase):
    def test_get_tokens_for_user_returns_access_and_refresh(self):
        suffix = uuid4().hex[:8]
        role = Role.objects.create(role_name=f"Admin-{suffix}")
        department = Department.objects.create(
            department_name=f"Computer Science & Engineering {suffix}",
            department_shortname="CSE",
        )
        user = User.objects.create(
            username=f"admin2-{suffix}",
            email=f"admin2-{suffix}@test.com",
            password="pass123",
            role=role,
            department=department,
        )

        tokens = get_tokens_for_user(user)

        self.assertIn("access", tokens)
        self.assertIn("refresh", tokens)
        self.assertTrue(tokens["access"])
        self.assertTrue(tokens["refresh"])
