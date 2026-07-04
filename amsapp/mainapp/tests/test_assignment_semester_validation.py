from datetime import timedelta
from io import StringIO
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    AdmissionResult,
    Department,
    Exam,
    ExamSchedule,
    Role,
    StudentAssignTeacherExam,
    Students,
    User,
)
from ..tokens import get_tokens_for_user


class AssignmentSemesterValidationTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]

        self.admin_role = Role.objects.create(role_name=f"Admin-{suffix}")
        self.dept_cse = Department.objects.create(
            department_name=f"Computer Science & Engineering {suffix}",
            department_shortname="CSE",
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

        self.matching_student = Students.objects.create(
            username=f"match-{suffix}",
            password="pass123",
            f_id=f"F101-{suffix}",
            full_name="Matching Student",
            email=f"match-{suffix}@test.com",
            department_shortname="CSE",
            registration_semester="Spring 2026",
            ssc=90,
            hsc=95,
        )
        self.mismatched_student = Students.objects.create(
            username=f"mismatch-{suffix}",
            password="pass123",
            f_id=f"F102-{suffix}",
            full_name="Mismatched Student",
            email=f"mismatch-{suffix}@test.com",
            department_shortname="CSE",
            registration_semester="Fall 2025",
            ssc=88,
            hsc=89,
        )

    def test_bulk_assignment_rejects_cross_semester_students_atomically(self):
        response = self.client.post(
            "/api/student-assignments/assign-bulk/",
            {
                "student_ids": [self.matching_student.id, self.mismatched_student.id],
                "teacher_id": self.admin_user.id,
                "schedule_id": self.schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "SEMESTER_MISMATCH")
        self.assertEqual(response.data["exam_semester"], "Spring 2026")
        mismatched_ids = [item["id"] for item in response.data["mismatched_students"]]
        self.assertEqual(mismatched_ids, [self.mismatched_student.id])
        # All-or-nothing: the matching student must not be assigned either.
        self.assertFalse(
            StudentAssignTeacherExam.objects.filter(schedule=self.schedule).exists()
        )

    def test_bulk_assignment_with_matching_semester_succeeds(self):
        response = self.client.post(
            "/api/student-assignments/assign-bulk/",
            {
                "student_ids": [self.matching_student.id],
                "teacher_id": self.admin_user.id,
                "schedule_id": self.schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["data"]["created_count"], 1)

    def test_single_assignment_rejects_cross_semester_student(self):
        response = self.client.post(
            "/api/student-assignments/assign-single/",
            {
                "student_id": self.mismatched_student.id,
                "teacher_id": self.admin_user.id,
                "schedule_id": self.schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "SEMESTER_MISMATCH")
        self.assertFalse(
            StudentAssignTeacherExam.objects.filter(
                student=self.mismatched_student, schedule=self.schedule
            ).exists()
        )

    def test_single_assignment_with_matching_semester_succeeds(self):
        response = self.client.post(
            "/api/student-assignments/assign-single/",
            {
                "student_id": self.matching_student.id,
                "teacher_id": self.admin_user.id,
                "schedule_id": self.schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_legacy_unnormalized_semester_text_is_not_flagged(self):
        # queryset.update() bypasses Students.save() normalization, simulating
        # legacy rows stored before semester values were canonicalized.
        Students.objects.filter(id=self.matching_student.id).update(
            registration_semester="spring  2026"
        )

        response = self.client.post(
            "/api/student-assignments/assign-bulk/",
            {
                "student_ids": [self.matching_student.id],
                "teacher_id": self.admin_user.id,
                "schedule_id": self.schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_bulk_assignment_rejects_second_exam_in_same_semester(self):
        StudentAssignTeacherExam.objects.create(
            student=self.matching_student,
            teacher=self.admin_user,
            exam=self.exam,
            schedule=self.schedule,
        )
        second_exam = Exam.objects.create(
            department="CSE",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )
        second_schedule = ExamSchedule.objects.create(
            exam=second_exam,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            is_active=True,
        )

        response = self.client.post(
            "/api/student-assignments/assign-bulk/",
            {
                "student_ids": [self.matching_student.id],
                "teacher_id": self.admin_user.id,
                "schedule_id": second_schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "DUPLICATE_SEMESTER_ASSIGNMENT")
        self.assertFalse(
            StudentAssignTeacherExam.objects.filter(exam=second_exam).exists()
        )

    def test_single_assignment_rejects_second_exam_in_same_semester(self):
        StudentAssignTeacherExam.objects.create(
            student=self.matching_student,
            teacher=self.admin_user,
            exam=self.exam,
            schedule=self.schedule,
        )
        second_exam = Exam.objects.create(
            department="CSE",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )
        second_schedule = ExamSchedule.objects.create(
            exam=second_exam,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            is_active=True,
        )

        response = self.client.post(
            "/api/student-assignments/assign-single/",
            {
                "student_id": self.matching_student.id,
                "teacher_id": self.admin_user.id,
                "schedule_id": second_schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "DUPLICATE_SEMESTER_ASSIGNMENT")

    def test_second_schedule_of_same_exam_still_allowed(self):
        StudentAssignTeacherExam.objects.create(
            student=self.matching_student,
            teacher=self.admin_user,
            exam=self.exam,
            schedule=self.schedule,
        )
        later_schedule = ExamSchedule.objects.create(
            exam=self.exam,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, hours=2),
            is_active=True,
        )

        response = self.client.post(
            "/api/student-assignments/assign-bulk/",
            {
                "student_ids": [self.matching_student.id],
                "teacher_id": self.admin_user.id,
                "schedule_id": later_schedule.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_results_endpoint_reports_unconfigured_exam_semesters(self):
        # No DepartmentThreshold exists, so absent generation is silently
        # blocked — the endpoint must say so.
        response = self.client.get(
            "/api/admission/results/",
            {"department_id": self.dept_cse.id, "semester": "Spring 2026"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["configuration_missing"])
        self.assertIn("Spring 2026", response.data["unconfigured_exam_semesters"])

    def test_diagnose_absent_marking_command_reports_blockers(self):
        # One cross-semester assignment whose schedule has already ended and
        # has no AdmissionResult row: hits all three report sections.
        ended_schedule = ExamSchedule.objects.create(
            exam=self.exam,
            start_time=timezone.now() - timedelta(hours=3),
            end_time=timezone.now() - timedelta(hours=1),
            is_active=True,
        )
        StudentAssignTeacherExam.objects.create(
            student=self.mismatched_student,
            teacher=self.admin_user,
            exam=self.exam,
            schedule=ended_schedule,
        )
        self.assertFalse(AdmissionResult.objects.filter(exam=self.exam).exists())

        output = StringIO()
        call_command("diagnose_absent_marking", stdout=output)
        report = output.getvalue()

        self.assertIn("1. Cross-semester assignments: 1", report)
        self.assertIn("2. Ended assignments with no AdmissionResult row: 1", report)
        self.assertIn("NO THRESHOLD CONFIG", report)
        self.assertIn(self.mismatched_student.username, report)

    def test_diagnose_absent_marking_command_reports_clean_state(self):
        output = StringIO()
        call_command(
            "diagnose_absent_marking",
            "--semester",
            "Summer 2030",
            stdout=output,
        )
        report = output.getvalue()

        self.assertIn("1. Cross-semester assignments: 0", report)
        self.assertIn("2. Ended assignments with no AdmissionResult row: 0", report)
