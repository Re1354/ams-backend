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
)
from ..models.viva_marks import VivaMarks
from ..tokens import get_tokens_for_user


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

    def set_thresholds(self, cse_threshold=60.0, eee_threshold=70.0):
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_cse,
            min_threshold_mark=cse_threshold,
        )
        DepartmentThreshold.objects.create(
            exam=self.exam,
            department=self.dept_eee,
            min_threshold_mark=eee_threshold,
        )

    def test_set_threshold_mapping_success(self):
        response = self.client.post(
            "/api/admission/threshold-mapping/",
            {
                "exam_id": self.exam.id,
                "mappings": [
                    {"department_id": self.dept_cse.id, "threshold": 60.0},
                    {"department_id": self.dept_eee.id, "threshold": 75.0},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["created_count"], 2)
        self.assertEqual(
            DepartmentThreshold.objects.filter(exam=self.exam).count(),
            2,
        )

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
        self.assertEqual(response.data["status_counts"]["WAITING"], 1)
        self.assertEqual(response.data["status_counts"]["REJECTED"], 1)
        self.assertEqual(response.data["status_counts"]["ABSENT"], 1)

        result1 = AdmissionResult.objects.get(student=self.student1, exam=self.exam)
        result2 = AdmissionResult.objects.get(student=self.student2, exam=self.exam)
        result3 = AdmissionResult.objects.get(student=self.student3, exam=self.exam)

        self.assertEqual(result1.weighted_total_marks, 70.0)
        self.assertEqual(result1.result_status, "WAITING")
        self.assertTrue(result1.is_selected)

        self.assertEqual(result2.weighted_total_marks, 50.0)
        self.assertEqual(result2.result_status, "REJECTED")
        self.assertFalse(result2.is_selected)

        self.assertEqual(result3.result_status, "ABSENT")
        self.assertFalse(result3.attended_exam)

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
            f"/api/admission/results/?department_id={self.dept_cse.id}&semester=Spring 2026&result_status=WAITING"
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
        self.assertEqual(refreshed.result_status, "WAITING")


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
