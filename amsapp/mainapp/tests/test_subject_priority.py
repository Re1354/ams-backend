from uuid import uuid4
from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    AdmissionResult,
    Department,
    DepartmentThreshold,
    Exam,
    Role,
    RoleMenu,
    Students,
    Subject,
    SubjectDepartment,
    SubjectPriority,
    User,
)
from ..services.admission_calculator import (
    apply_semester_result_statuses,
    build_candidate_tiebreak_key,
    extract_subject_mark,
    get_priority_subject_names_for_department,
)
from ..tokens import get_tokens_for_user


class SubjectPriorityTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]

        self.superadmin_role, _ = Role.objects.get_or_create(role_name="superadmin")
        self.admin_user = User.objects.create(
            username=f"admin_{suffix}",
            email=f"admin_{suffix}@example.com",
            password=make_password("Secret123!"),
            role=self.superadmin_role,
        )
        tokens = get_tokens_for_user(self.admin_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        # Departments
        self.dept_cse = Department.objects.create(
            department_name=f"Computer Science and Engineering {suffix}",
            department_shortname="CSE",
        )
        self.dept_eee = Department.objects.create(
            department_name=f"Electrical and Electronic Engineering {suffix}",
            department_shortname="EEE",
        )

        # Subjects
        self.sub_it = Subject.objects.create(subject_name=f"IT_{suffix}")
        self.sub_math = Subject.objects.create(subject_name=f"Math_{suffix}")
        self.sub_physics = Subject.objects.create(subject_name=f"Physics_{suffix}")
        self.sub_english = Subject.objects.create(subject_name=f"English_{suffix}")
        self.sub_gk = Subject.objects.create(subject_name=f"GK_{suffix}")

        self.suffix = suffix

    def test_extract_subject_mark(self):
        """Test extraction of subject marks from various JSON formats."""
        data_dict = {
            self.sub_it.subject_name: {"marks_obtained": 85.5, "total_questions": 10},
            self.sub_math.subject_name: {"marks": 90.0},
            self.sub_physics.subject_name: 75.0,
        }
        self.assertEqual(extract_subject_mark(data_dict, self.sub_it.subject_name), 85.5)
        self.assertEqual(extract_subject_mark(data_dict, self.sub_math.subject_name), 90.0)
        self.assertEqual(extract_subject_mark(data_dict, self.sub_physics.subject_name), 75.0)
        # Case-insensitive check
        self.assertEqual(extract_subject_mark(data_dict, self.sub_it.subject_name.lower()), 85.5)
        # Missing subject
        self.assertEqual(extract_subject_mark(data_dict, "UnknownSubject"), 0.0)

    def test_subject_priority_api_save_and_retrieve(self):
        """Test configuring and retrieving department subject priorities via REST API."""
        # 1. Save priorities for CSE: IT > Math > Physics > English > GK
        save_url = "/api/subject-priorities/save/"
        payload = {
            "department_id": self.dept_cse.id,
            "subject_ids": [
                self.sub_it.id,
                self.sub_math.id,
                self.sub_physics.id,
                self.sub_english.id,
                self.sub_gk.id,
            ],
        }
        response = self.client.post(save_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        priorities = response.data["data"]["priorities"]
        self.assertEqual(len(priorities), 5)
        self.assertEqual(priorities[0]["subject_id"], self.sub_it.id)
        self.assertEqual(priorities[0]["priority"], 1)
        self.assertEqual(priorities[1]["subject_id"], self.sub_math.id)
        self.assertEqual(priorities[1]["priority"], 2)

        # 2. Get department priority details
        detail_url = f"/api/subject-priorities/department/{self.dept_cse.id}/"
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["department_id"], self.dept_cse.id)
        self.assertEqual(len(data["priorities"]), 5)
        self.assertIn("available_subjects", data)

        # 3. Get all subject priorities
        all_url = "/api/subject-priorities/"
        response = self.client.get(all_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cse_entry = next(
            (d for d in response.data["data"] if d["department_id"] == self.dept_cse.id), None
        )
        self.assertIsNotNone(cse_entry)
        self.assertEqual(len(cse_entry["priorities"]), 5)

        # 4. Duplicate subject validation
        dup_payload = {
            "department_id": self.dept_cse.id,
            "subject_ids": [self.sub_it.id, self.sub_it.id],
        }
        response = self.client.post(save_url, dup_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("subject_ids", response.data["errors"])

        # 5. Delete / reset department priorities
        del_url = f"/api/subject-priorities/department/{self.dept_cse.id}/delete/"
        response = self.client.delete(del_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(SubjectPriority.objects.filter(department=self.dept_cse).count(), 0)

    def test_tiebreak_differing_total_marks_preserved(self):
        """
        Verify rule: When students have different total marks,
        the student with higher total marks is ALWAYS ranked higher,
        regardless of subject marks.
        """
        priority_subjects = [self.sub_it.subject_name, self.sub_math.subject_name]

        class DummyCandidate:
            def __init__(self, id, total, it_mark, math_mark):
                self.id = id
                self.student_id = id
                self.weighted_total_marks = total
                self.written_viva_total = total
                self.mcq_marks = total
                self.subject_wise_marks = {
                    priority_subjects[0]: {"marks_obtained": it_mark},
                    priority_subjects[1]: {"marks_obtained": math_mark},
                }

        cand_a = DummyCandidate(1, 85.0, 70, 70)  # Total 85, lower subject marks
        cand_b = DummyCandidate(2, 80.0, 95, 95)  # Total 80, higher subject marks

        candidates = [cand_b, cand_a]
        candidates.sort(key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))

        # cand_a must be first because 85.0 > 80.0
        self.assertEqual(candidates[0].id, 1)
        self.assertEqual(candidates[1].id, 2)

    def test_tiebreak_priority_1_subject_comparison(self):
        """
        CSE: IT > Math > Physics
        Student A: Total 80, IT 85, Math 95
        Student B: Total 80, IT 90, Math 70
        Since IT is priority 1 and Student B has 90 > 85, Student B must rank higher!
        """
        priority_subjects = [
            self.sub_it.subject_name,
            self.sub_math.subject_name,
            self.sub_physics.subject_name,
        ]

        class DummyCandidate:
            def __init__(self, id, total, it_mark, math_mark):
                self.id = id
                self.student_id = id
                self.weighted_total_marks = total
                self.written_viva_total = total
                self.mcq_marks = total
                self.subject_wise_marks = {
                    priority_subjects[0]: {"marks_obtained": it_mark},
                    priority_subjects[1]: {"marks_obtained": math_mark},
                }

        student_a = DummyCandidate(1, 80.0, 85, 95)
        student_b = DummyCandidate(2, 80.0, 90, 70)

        candidates = [student_a, student_b]
        candidates.sort(key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))

        self.assertEqual(candidates[0].id, 2, "Student B (IT=90) should rank above Student A (IT=85)")
        self.assertEqual(candidates[1].id, 1)

    def test_tiebreak_priority_2_subject_comparison(self):
        """
        CSE: IT > Math > Physics
        Student A: Total 80, IT 90, Math 95
        Student B: Total 80, IT 90, Math 80
        Since IT is tied (90 vs 90), Math (priority 2) determines winner: Student A has 95 > 80!
        """
        priority_subjects = [
            self.sub_it.subject_name,
            self.sub_math.subject_name,
            self.sub_physics.subject_name,
        ]

        class DummyCandidate:
            def __init__(self, id, total, it_mark, math_mark):
                self.id = id
                self.student_id = id
                self.weighted_total_marks = total
                self.written_viva_total = total
                self.mcq_marks = total
                self.subject_wise_marks = {
                    priority_subjects[0]: {"marks_obtained": it_mark},
                    priority_subjects[1]: {"marks_obtained": math_mark},
                }

        student_a = DummyCandidate(1, 80.0, 90, 95)
        student_b = DummyCandidate(2, 80.0, 90, 80)

        candidates = [student_b, student_a]
        candidates.sort(key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))

        self.assertEqual(candidates[0].id, 1, "Student A (Math=95) should beat Student B (Math=80)")
        self.assertEqual(candidates[1].id, 2)

    def test_department_specific_priority_rules(self):
        """
        Configure different priority orders for CSE and EEE:
        CSE: IT > Math > Physics
        EEE: Physics > Math > IT
        Verify get_priority_subject_names_for_department returns distinct orders.
        """
        # Configure CSE: IT (1), Math (2), Physics (3)
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_it, priority=1)
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_math, priority=2)
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_physics, priority=3)

        # Configure EEE: Physics (1), Math (2), IT (3)
        SubjectPriority.objects.create(department=self.dept_eee, subject=self.sub_physics, priority=1)
        SubjectPriority.objects.create(department=self.dept_eee, subject=self.sub_math, priority=2)
        SubjectPriority.objects.create(department=self.dept_eee, subject=self.sub_it, priority=3)

        cse_order = get_priority_subject_names_for_department(self.dept_cse)
        eee_order = get_priority_subject_names_for_department(self.dept_eee)

        self.assertEqual(cse_order, [self.sub_it.subject_name, self.sub_math.subject_name, self.sub_physics.subject_name])
        self.assertEqual(eee_order, [self.sub_physics.subject_name, self.sub_math.subject_name, self.sub_it.subject_name])

    def test_semester_result_status_selection_tiebreak(self):
        """
        Integration test with database AdmissionResult and apply_semester_result_statuses.
        With seat_limit=1:
        Student A: total=80.0, IT=85, Math=95
        Student B: total=80.0, IT=90, Math=70
        With CSE priority IT > Math:
        Student B must be SELECTED, Student A must be WAITING.
        """
        semester = "Spring 2026"
        exam = Exam.objects.create(
            department=self.dept_cse.department_shortname,
            semester=semester,
            total_marks=100,
            total_questions=50,
            duration_minutes=60,
        )

        # Configure CSE Priority: IT > Math
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_it, priority=1)
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_math, priority=2)

        # Configure Threshold: 50.0 threshold, 1 seat, 1 waiting
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=semester,
            min_threshold_mark=50.0,
            seat_limit=1,
            waiting_student_limit=1,
        )

        student_a = Students.objects.create(
            username=f"student_a_{self.suffix}",
            full_name="Student A",
            f_id="FID001",
            department_shortname="CSE",
            registration_semester=semester,
        )
        student_b = Students.objects.create(
            username=f"student_b_{self.suffix}",
            full_name="Student B",
            f_id="FID002",
            department_shortname="CSE",
            registration_semester=semester,
        )

        # Create AdmissionResult records
        res_a = AdmissionResult.objects.create(
            exam=exam,
            student=student_a,
            department=self.dept_cse,
            mcq_marks=40.0,
            viva_marks=40.0,
            weighted_total_marks=80.0,
            attended_exam=True,
            subject_wise_marks={
                self.sub_it.subject_name: {"marks_obtained": 85.0},
                self.sub_math.subject_name: {"marks_obtained": 95.0},
            },
        )
        res_b = AdmissionResult.objects.create(
            exam=exam,
            student=student_b,
            department=self.dept_cse,
            mcq_marks=40.0,
            viva_marks=40.0,
            weighted_total_marks=80.0,
            attended_exam=True,
            subject_wise_marks={
                self.sub_it.subject_name: {"marks_obtained": 90.0},
                self.sub_math.subject_name: {"marks_obtained": 70.0},
            },
        )

        # Execute apply_semester_result_statuses
        result = apply_semester_result_statuses(
            department=self.dept_cse,
            semester=semester,
            threshold_value=50.0,
            seat_limit=1,
            waiting_student_limit=1,
        )
        self.assertTrue(result["success"])

        res_a.refresh_from_db()
        res_b.refresh_from_db()

        # Student B had IT=90 vs Student A's IT=85, so Student B got the single available seat!
        self.assertEqual(res_b.result_status, "SELECTED")
        self.assertTrue(res_b.is_selected)

        self.assertEqual(res_a.result_status, "WAITING")
        self.assertFalse(res_a.is_selected)
