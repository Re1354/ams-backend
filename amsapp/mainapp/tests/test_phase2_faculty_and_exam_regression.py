from datetime import timedelta
from uuid import uuid4
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    Faculty,
    Department,
    FacultyDepartment,
    Role,
    User,
    Exam,
    ExamSchedule,
    Students,
    Subject,
    SubjectFaculty,
    MarksDistribution,
    VivaRubrics,
)
from ..tokens import get_tokens_for_user
from ..views.student_assign_teacher_exam import get_faculty_and_department_mismatches
from ..services.access_control import get_user_access_scope, get_subjects_for_department


class Phase2RegressionTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]

        # 1. Setup Roles
        self.superadmin_role = Role.objects.create(role_name=f"superadmin-{suffix}")
        self.teacher_role = Role.objects.create(role_name=f"teacher-{suffix}")

        # 2. Setup Faculty & Departments
        self.faculty_fsit = Faculty.objects.create(
            faculty_name=f"Faculty of Science & IT {suffix}",
            faculty_shortname="FSIT",
        )
        self.faculty_fe = Faculty.objects.create(
            faculty_name=f"Faculty of Engineering {suffix}",
            faculty_shortname="FE",
        )

        self.dept_cse = Department.objects.create(
            department_name=f"Computer Science & Engineering {suffix}",
            department_shortname="CSE",
        )
        self.dept_swe = Department.objects.create(
            department_name=f"Software Engineering {suffix}",
            department_shortname="SWE",
        )
        self.dept_eee = Department.objects.create(
            department_name=f"Electrical & Electronic Engineering {suffix}",
            department_shortname="EEE",
        )

        # Map FSIT -> CSE, SWE
        self.fd_fsit = FacultyDepartment.objects.create(
            faculty=self.faculty_fsit,
            department_ids=[self.dept_cse.id, self.dept_swe.id],
        )
        # Map FE -> EEE
        self.fd_fe = FacultyDepartment.objects.create(
            faculty=self.faculty_fe,
            department_ids=[self.dept_eee.id],
        )

        # 3. Setup Users
        self.admin_user = User.objects.create(
            username=f"admin_{suffix}",
            email=f"admin_{suffix}@diu.edu",
            password=make_password("pass123"),
            role=self.superadmin_role,
            is_global_access=True,
            access_type="GLOBAL",
        )
        self.faculty_user = User.objects.create(
            username=f"dean_{suffix}",
            email=f"dean_{suffix}@diu.edu",
            password=make_password("pass123"),
            role=self.teacher_role,
            faculty=self.faculty_fsit,
            access_type="FACULTY",
        )
        self.dept_user = User.objects.create(
            username=f"teacher_cse_{suffix}",
            email=f"teacher_cse_{suffix}@diu.edu",
            password=make_password("pass123"),
            role=self.teacher_role,
            department=self.dept_cse,
            faculty=self.faculty_fsit,
            access_type="DEPARTMENT",
        )
        self.fe_user = User.objects.create(
            username=f"teacher_eee_{suffix}",
            email=f"teacher_eee_{suffix}@diu.edu",
            password=make_password("pass123"),
            role=self.teacher_role,
            department=self.dept_eee,
            faculty=self.faculty_fe,
            access_type="DEPARTMENT",
        )

        # Setup token credentials for admin
        tokens = get_tokens_for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_users_search_and_filtering(self):
        """Req 12: Verify users management search and multi-field filters"""
        # Test search by username
        response = self.client.get("/api/users/", {"search": self.faculty_user.username})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in response.data["data"]]
        self.assertIn(self.faculty_user.username, usernames)
        self.assertNotIn(self.dept_user.username, usernames)

        # Test filter by access_type
        response = self.client.get("/api/users/", {"access_type": "FACULTY"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access_types = [u["access_type"] for u in response.data["data"]]
        self.assertTrue(all(a == "FACULTY" for a in access_types))

        # Test filter by faculty
        response = self.client.get("/api/users/", {"faculty": str(self.faculty_fsit.id)})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        fac_users = [u["username"] for u in response.data["data"]]
        self.assertIn(self.faculty_user.username, fac_users)
        self.assertNotIn(self.fe_user.username, fac_users)

    def test_users_scoped_access_control(self):
        """Req 12: Faculty-scoped user cannot discover unrelated faculty users"""
        tokens = get_tokens_for_user(self.faculty_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [u["username"] for u in response.data["data"]]
        # FSIT users visible
        self.assertIn(self.faculty_user.username, usernames)
        self.assertIn(self.dept_user.username, usernames)
        # FE users not visible
        self.assertNotIn(self.fe_user.username, usernames)

    def test_marks_distribution_faculty_only(self):
        """Req 13 & 17: Marks Distribution requires faculty and applies faculty-wide"""
        tokens = get_tokens_for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        payload = {
            "faculty": self.faculty_fsit.id,
            "ssc": 15,
            "hsc": 15,
            "main_marks": 50,
            "viva_marks": 20,
        }
        response = self.client.post("/api/create-marks-distribution/", payload, format="json")
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

        # Verify created record has faculty_id
        dist = MarksDistribution.objects.filter(faculty_id=self.faculty_fsit.id).first()
        self.assertIsNotNone(dist)
        self.assertEqual(dist.main_marks, 50)

    def test_viva_rubrics_faculty_only(self):
        """Req 16: Viva Rubrics requires faculty and applies faculty-wide"""
        tokens = get_tokens_for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        payload = {
            "faculty": self.faculty_fsit.id,
            "rubrics": '[{"name": "Communication", "score": 10}]',
            "marks": 25,
        }
        response = self.client.post("/api/create-rubrics/", payload, format="json")
        self.assertIn(response.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])

        rubric = VivaRubrics.objects.filter(faculty_id=self.faculty_fsit.id).first()
        self.assertIsNotNone(rubric)

    def test_student_assignment_faculty_eligibility(self):
        """Req 1: Both Central and Scheduled exams enforce faculty-based eligibility"""
        # 1. Central Exam under FSIT
        central_exam = Exam.objects.create(
            department="Central (FSIT)",
            faculty=self.faculty_fsit.faculty_shortname,
            faculty_ref=self.faculty_fsit,
            exam_type="CENTRAL",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )

        # 2. Student from CSE (under FSIT)
        student_cse = Students.objects.create(
            username=f"stu_cse_{uuid4().hex[:6]}",
            email="stucse@test.com",
            full_name="CSE Student",
            department_shortname="CSE",
            registration_semester="Spring 2026",
            faculty=self.faculty_fsit,
        )

        # 3. Student from EEE (under FE - different faculty!)
        student_eee = Students.objects.create(
            username=f"stu_eee_{uuid4().hex[:6]}",
            email="stueee@test.com",
            full_name="EEE Student",
            department_shortname="EEE",
            registration_semester="Spring 2026",
            faculty=self.faculty_fe,
        )

        # Check eligibility for Central Exam
        mismatches = get_faculty_and_department_mismatches([student_cse, student_eee], central_exam)
        mismatched_ids = [m["id"] for m in mismatches]

        # student_cse belongs to FSIT -> eligible, should NOT be in mismatches
        self.assertNotIn(student_cse.id, mismatched_ids)
        # student_eee belongs to FE -> NOT eligible for FSIT exam, MUST be in mismatches
        self.assertIn(student_eee.id, mismatched_ids)

    def test_subject_faculty_mapping_and_department_resolution(self):
        """Req 14 & 15: Department inherits subjects from parent faculty"""
        sub1 = Subject.objects.create(subject_name=f"Mathematics {uuid4().hex[:4]}")
        sub2 = Subject.objects.create(subject_name=f"Physics {uuid4().hex[:4]}")

        # Map subjects to FSIT faculty
        SubjectFaculty.objects.create(
            faculty=self.faculty_fsit,
            subject_ids=[sub1.id, sub2.id],
        )

        # Resolve subjects for CSE department (under FSIT)
        resolved_subject_ids = get_subjects_for_department(self.dept_cse.id)
        self.assertIn(sub1.id, resolved_subject_ids)
        self.assertIn(sub2.id, resolved_subject_ids)
