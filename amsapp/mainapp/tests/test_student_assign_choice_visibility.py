from uuid import uuid4
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import (
    Department,
    Exam,
    ExamSchedule,
    Faculty,
    FacultyDepartment,
    Role,
    Students,
    StudentAssignTeacherExam,
    User,
)
from ..views.student_assign_teacher_exam import get_faculty_and_department_mismatches


class StudentAssignChoiceVisibilityTestCase(TestCase):
    """
    Comprehensive tests for Student Assign visibility based on
    the student's complete department Choice List.
    """

    def setUp(self):
        self.client = APIClient()

        # Roles
        self.admin_role, _ = Role.objects.get_or_create(role_name="superadmin")
        self.dept_role, _ = Role.objects.get_or_create(role_name="department_admin")
        self.faculty_role, _ = Role.objects.get_or_create(role_name="faculty_admin")
        self.teacher_role, _ = Role.objects.get_or_create(role_name="teacher")

        # Faculties
        self.faculty_fsit = Faculty.objects.create(
            faculty_name="Faculty of Science and Information Technology",
            faculty_shortname="FSIT",
        )
        self.faculty_fe = Faculty.objects.create(
            faculty_name="Faculty of Engineering",
            faculty_shortname="FE",
        )

        # Departments
        self.dept_cse = Department.objects.create(
            department_name="Computer Science and Engineering",
            department_shortname="CSE",
        )
        self.dept_swe = Department.objects.create(
            department_name="Software Engineering",
            department_shortname="SWE",
        )
        self.dept_mct = Department.objects.create(
            department_name="Multimedia and Creative Technology",
            department_shortname="MCT",
        )
        self.dept_eee = Department.objects.create(
            department_name="Electrical and Electronic Engineering",
            department_shortname="EEE",
        )

        # Map FSIT -> [CSE, SWE, MCT], FE -> [EEE]
        FacultyDepartment.objects.create(
            faculty=self.faculty_fsit,
            department_ids=[self.dept_cse.id, self.dept_swe.id, self.dept_mct.id],
        )
        FacultyDepartment.objects.create(
            faculty=self.faculty_fe,
            department_ids=[self.dept_eee.id],
        )

        # Users
        # 1. Global / Superadmin
        self.user_global = User.objects.create(
            username=f"global_{uuid4().hex[:6]}",
            email="global@diu.edu.bd",
            role=self.admin_role,
            is_global_access=True,
            access_type="GLOBAL",
        )
        # 2. Department Users: CSE, SWE, MCT, EEE
        self.user_cse = User.objects.create(
            username=f"dept_cse_{uuid4().hex[:6]}",
            email="cse_admin@diu.edu.bd",
            role=self.dept_role,
            department=self.dept_cse,
            access_type="DEPARTMENT",
        )
        self.user_swe = User.objects.create(
            username=f"dept_swe_{uuid4().hex[:6]}",
            email="swe_admin@diu.edu.bd",
            role=self.dept_role,
            department=self.dept_swe,
            access_type="DEPARTMENT",
        )
        self.user_mct = User.objects.create(
            username=f"dept_mct_{uuid4().hex[:6]}",
            email="mct_admin@diu.edu.bd",
            role=self.dept_role,
            department=self.dept_mct,
            access_type="DEPARTMENT",
        )
        self.user_eee = User.objects.create(
            username=f"dept_eee_{uuid4().hex[:6]}",
            email="eee_admin@diu.edu.bd",
            role=self.dept_role,
            department=self.dept_eee,
            access_type="DEPARTMENT",
        )
        # 3. Faculty User: FSIT
        self.user_fsit = User.objects.create(
            username=f"fac_fsit_{uuid4().hex[:6]}",
            email="fsit_admin@diu.edu.bd",
            role=self.faculty_role,
            faculty=self.faculty_fsit,
            access_type="FACULTY",
        )

        # 4. Teacher
        self.teacher_cse = User.objects.create(
            username=f"teacher_cse_{uuid4().hex[:6]}",
            email="teach_cse@diu.edu.bd",
            role=self.teacher_role,
            department=self.dept_cse,
            access_type="DEPARTMENT",
        )

        # Students
        # Student 1: Choice 1: CSE, Choice 2: SWE, Choice 3: MCT
        self.student_1 = Students.objects.create(
            username="student_1_cse_swe_mct",
            f_id="FID-001",
            full_name="Alice Smith",
            email="alice@test.com",
            department_shortname="CSE",
            registration_semester="Spring 2026",
            faculty=self.faculty_fsit,
            department_choices=[
                {"department_id": self.dept_cse.id, "priority": 1},
                {"department_id": self.dept_swe.id, "priority": 2},
                {"department_id": self.dept_mct.id, "priority": 3},
            ],
        )

        # Student 2: Choice 1: SWE, Choice 2: CSE
        self.student_2 = Students.objects.create(
            username="student_2_swe_cse",
            f_id="FID-002",
            full_name="Bob Jones",
            email="bob@test.com",
            department_shortname="SWE",
            registration_semester="Spring 2026",
            faculty=self.faculty_fsit,
            department_choices=[
                {"department_id": self.dept_swe.id, "priority": 1},
                {"department_id": self.dept_cse.id, "priority": 2},
            ],
        )

        # Student 3: Choice 1: MCT only
        self.student_3 = Students.objects.create(
            username="student_3_mct_only",
            f_id="FID-003",
            full_name="Charlie Brown",
            email="charlie@test.com",
            department_shortname="MCT",
            registration_semester="Spring 2026",
            faculty=self.faculty_fsit,
            department_choices=[
                {"department_id": self.dept_mct.id, "priority": 1},
            ],
        )

        # Student 4: EEE only (under FE)
        self.student_eee = Students.objects.create(
            username="student_4_eee_only",
            f_id="FID-004",
            full_name="David Miller",
            email="david@test.com",
            department_shortname="EEE",
            registration_semester="Spring 2026",
            faculty=self.faculty_fe,
            department_choices=[
                {"department_id": self.dept_eee.id, "priority": 1},
            ],
        )

        # Student 5: Legacy student without department_choices (empty list), department_shortname="CSE"
        self.student_legacy_cse = Students.objects.create(
            username="student_5_legacy_cse",
            f_id="FID-005",
            full_name="Eve Legacy",
            email="eve@test.com",
            department_shortname="CSE",
            registration_semester="Spring 2026",
            faculty=self.faculty_fsit,
            department_choices=[],
        )

    def _auth(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # =========================================================================
    # Test A: First-choice department
    # =========================================================================
    def test_a_first_choice_and_all_choices_visibility(self):
        """
        Student 1 chose CSE first, SWE second, and MCT third.
        Verify CSE, SWE, and MCT admins can all see Student 1.
        """
        # CSE admin
        self._auth(self.user_cse)
        res_cse = self.client.get("/api/students/")
        self.assertEqual(res_cse.status_code, status.HTTP_200_OK)
        cse_ids = [s["id"] for s in res_cse.data["students"]]
        self.assertIn(self.student_1.id, cse_ids)

        # SWE admin
        self._auth(self.user_swe)
        res_swe = self.client.get("/api/students/")
        self.assertEqual(res_swe.status_code, status.HTTP_200_OK)
        swe_ids = [s["id"] for s in res_swe.data["students"]]
        self.assertIn(self.student_1.id, swe_ids)

        # MCT admin
        self._auth(self.user_mct)
        res_mct = self.client.get("/api/students/")
        self.assertEqual(res_mct.status_code, status.HTTP_200_OK)
        mct_ids = [s["id"] for s in res_mct.data["students"]]
        self.assertIn(self.student_1.id, mct_ids)

    # =========================================================================
    # Test B: Non-first-choice department
    # =========================================================================
    def test_b_non_first_choice_department_visibility(self):
        """
        Student 2 chose SWE first and CSE second.
        Verify CSE admin can see Student 2 even though CSE is choice 2 and department_shortname is SWE.
        """
        self._auth(self.user_cse)
        res = self.client.get("/api/students/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        visible_ids = [s["id"] for s in res.data["students"]]
        self.assertIn(self.student_2.id, visible_ids)

    # =========================================================================
    # Test C: Unrelated department
    # =========================================================================
    def test_c_unrelated_department_cannot_see_student(self):
        """
        Student 1 chose CSE, SWE, MCT.
        Verify EEE admin CANNOT see Student 1, Student 2, or Student 3.
        EEE admin can only see Student 4 (EEE).
        """
        self._auth(self.user_eee)
        res = self.client.get("/api/students/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        visible_ids = [s["id"] for s in res.data["students"]]
        self.assertNotIn(self.student_1.id, visible_ids)
        self.assertNotIn(self.student_2.id, visible_ids)
        self.assertNotIn(self.student_3.id, visible_ids)
        self.assertIn(self.student_eee.id, visible_ids)

    # =========================================================================
    # Test D: Duplicate choices or query joins
    # =========================================================================
    def test_d_no_duplicate_student_rows(self):
        """
        Ensure students appear exactly once in the student listing.
        """
        self._auth(self.user_cse)
        res = self.client.get("/api/students/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        returned_ids = [s["id"] for s in res.data["students"]]
        self.assertEqual(len(returned_ids), len(set(returned_ids)))

    # =========================================================================
    # Test E: Faculty access
    # =========================================================================
    def test_e_faculty_access_sees_all_faculty_departments(self):
        """
        FSIT faculty admin sees students whose choices include CSE, SWE, or MCT,
        but NOT EEE (which belongs to FE).
        """
        self._auth(self.user_fsit)
        res = self.client.get("/api/students/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        visible_ids = [s["id"] for s in res.data["students"]]
        self.assertIn(self.student_1.id, visible_ids)
        self.assertIn(self.student_2.id, visible_ids)
        self.assertIn(self.student_3.id, visible_ids)
        self.assertNotIn(self.student_eee.id, visible_ids)

    # =========================================================================
    # Test F: Global access
    # =========================================================================
    def test_f_global_access_sees_all_students(self):
        """
        Superadmin sees all students across all faculties and departments.
        """
        self._auth(self.user_global)
        res = self.client.get("/api/students/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        visible_ids = [s["id"] for s in res.data["students"]]
        self.assertIn(self.student_1.id, visible_ids)
        self.assertIn(self.student_2.id, visible_ids)
        self.assertIn(self.student_3.id, visible_ids)
        self.assertIn(self.student_eee.id, visible_ids)
        self.assertIn(self.student_legacy_cse.id, visible_ids)

    # =========================================================================
    # Test G: Exam compatibility (Scheduled & Central)
    # =========================================================================
    def test_g_exam_compatibility_scheduled_and_central(self):
        """
        Verify exam eligibility for Scheduled vs Central exams:
        - Student 2 (SWE choice 1, CSE choice 2) is ELIGIBLE for CSE Scheduled Exam.
        - Student 3 (MCT choice 1) is NOT eligible for CSE Scheduled Exam.
        - Both Student 2 and Student 3 are eligible for Central (FSIT) Exam.
        - Student 4 (EEE) is NOT eligible for Central (FSIT) Exam.
        """
        # CSE Scheduled Exam
        exam_cse_scheduled = Exam.objects.create(
            department="CSE",
            faculty="FSIT",
            faculty_ref=self.faculty_fsit,
            exam_type="SCHEDULED",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )

        # Central Exam (FSIT)
        exam_central_fsit = Exam.objects.create(
            department="Central (FSIT)",
            faculty="FSIT",
            faculty_ref=self.faculty_fsit,
            exam_type="CENTRAL",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )

        # Check CSE Scheduled Exam eligibility
        # Student 2 has CSE as 2nd choice -> eligible!
        mismatches_sched = get_faculty_and_department_mismatches(
            [self.student_1, self.student_2, self.student_3, self.student_eee],
            exam_cse_scheduled,
        )
        mismatched_ids = [m["id"] for m in mismatches_sched]
        self.assertNotIn(self.student_1.id, mismatched_ids)
        self.assertNotIn(self.student_2.id, mismatched_ids)  # Eligible because CSE is in choices!
        self.assertIn(self.student_3.id, mismatched_ids)      # Ineligible: MCT only
        self.assertIn(self.student_eee.id, mismatched_ids)    # Ineligible: EEE only

        # Check Central (FSIT) Exam eligibility
        mismatches_central = get_faculty_and_department_mismatches(
            [self.student_1, self.student_2, self.student_3, self.student_eee],
            exam_central_fsit,
        )
        central_mismatched_ids = [m["id"] for m in mismatches_central]
        self.assertNotIn(self.student_1.id, central_mismatched_ids)
        self.assertNotIn(self.student_2.id, central_mismatched_ids)
        self.assertNotIn(self.student_3.id, central_mismatched_ids)
        self.assertIn(self.student_eee.id, central_mismatched_ids)  # EEE belongs to FE!

    # =========================================================================
    # Test H: Already-assigned students handling
    # =========================================================================
    def test_h_already_assigned_students_endpoint(self):
        """
        Verify that once a student is assigned, get_assigned_student_ids returns their ID.
        """
        exam = Exam.objects.create(
            department="CSE",
            faculty="FSIT",
            faculty_ref=self.faculty_fsit,
            exam_type="SCHEDULED",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )
        schedule = ExamSchedule.objects.create(
            exam=exam,
            start_time="2026-03-01T10:00:00Z",
            end_time="2026-03-01T12:00:00Z",
            is_active=True,
        )

        # Assign student_2 (CSE choice 2)
        StudentAssignTeacherExam.objects.create(
            student=self.student_2,
            teacher=self.teacher_cse,
            schedule=schedule,
            exam=exam,
        )

        self._auth(self.user_cse)
        res = self.client.get("/api/student-assignments/assigned-student-ids/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(self.student_2.id, res.data["student_ids"])

        # Also verify get_all_assignments includes the assignment for CSE admin
        res_assign = self.client.get("/api/student-assignments/")
        self.assertEqual(res_assign.status_code, status.HTTP_200_OK)
        assign_ids = [a["student"] for a in res_assign.data["data"]]
        self.assertIn(self.student_2.id, assign_ids)

    # =========================================================================
    # Test I: Search and semester filters
    # =========================================================================
    def test_i_search_and_semester_filters(self):
        """
        Verify search and semester filters work with choice-list visible students.
        """
        self._auth(self.user_cse)

        # Search by student name
        res_search_name = self.client.get("/api/students/", {"search": "Bob"})
        self.assertEqual(res_search_name.status_code, status.HTTP_200_OK)
        ids = [s["id"] for s in res_search_name.data["students"]]
        self.assertIn(self.student_2.id, ids)

        # Search by registration semester
        res_sem = self.client.get("/api/students/", {"registration_semester": "Spring 2026"})
        self.assertEqual(res_sem.status_code, status.HTTP_200_OK)
        ids_sem = [s["id"] for s in res_sem.data["students"]]
        self.assertIn(self.student_1.id, ids_sem)
        self.assertIn(self.student_2.id, ids_sem)

        # Non-matching semester
        res_no_sem = self.client.get("/api/students/", {"registration_semester": "Fall 2024"})
        self.assertEqual(res_no_sem.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_no_sem.data["students"]), 0)

    # =========================================================================
    # Test J: Backend authorization enforcement
    # =========================================================================
    def test_j_backend_authorization_prevents_unauthorized_assignment(self):
        """
        Attempting to assign an unauthorized student (e.g. EEE admin trying to assign Student 1)
        must return HTTP 403 FORBIDDEN.
        """
        exam_eee = Exam.objects.create(
            department="EEE",
            faculty="FE",
            faculty_ref=self.faculty_fe,
            exam_type="SCHEDULED",
            semester="Spring 2026",
            total_questions=10,
            present_question=10,
            total_marks=100,
            duration_minutes=120,
        )
        schedule_eee = ExamSchedule.objects.create(
            exam=exam_eee,
            start_time="2026-03-01T10:00:00Z",
            end_time="2026-03-01T12:00:00Z",
            is_active=True,
        )

        # EEE admin attempts to assign Student 1 (who only chose CSE, SWE, MCT)
        self._auth(self.user_eee)
        payload = {
            "student_ids": [self.student_1.id],
            "teacher_id": self.user_eee.id,
            "schedule_id": schedule_eee.id,
        }
        res = self.client.post("/api/student-assignments/assign-bulk/", payload, format="json")
        self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

        # Also verify single assign endpoint enforces authorization
        single_payload = {
            "student_id": self.student_1.id,
            "teacher_id": self.user_eee.id,
            "schedule_id": schedule_eee.id,
        }
        single_res = self.client.post("/api/student-assignments/assign-single/", single_payload, format="json")
        self.assertIn(single_res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])

        # Verify get_student_by_id endpoint blocks unauthorized access
        detail_res = self.client.get(f"/api/students/{self.student_1.id}/")
        self.assertEqual(detail_res.status_code, status.HTTP_403_FORBIDDEN)
