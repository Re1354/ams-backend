from uuid import uuid4
from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    AdmissionConfiguration,
    AdmissionResult,
    Department,
    DepartmentThreshold,
    Exam,
    Faculty,
    FacultyDepartment,
    Role,
    Students,
    Subject,
    SubjectPriority,
    User,
)
from ..serializers.admission_result import AdmissionResultSerializer
from ..services.admission_calculator import (
    apply_semester_result_statuses,
    build_candidate_tiebreak_key,
    calculate_admission_results,
    get_applicant_id_sort_key,
    get_effective_department_choices,
    get_priority_subject_names_for_department,
)
from ..tokens import get_tokens_for_user


class AdmissionAllocationAlgorithmTests(APITestCase):
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

        # Departments: CSE, SWE, MCT
        self.dept_cse = Department.objects.create(
            department_name=f"Computer Science and Engineering {suffix}",
            department_shortname="CSE",
        )
        self.dept_swe = Department.objects.create(
            department_name=f"Software Engineering {suffix}",
            department_shortname="SWE",
        )
        self.dept_mct = Department.objects.create(
            department_name=f"Multimedia and Creative Technology {suffix}",
            department_shortname="MCT",
        )

        # Subjects
        self.sub_it = Subject.objects.create(subject_name=f"IT_{suffix}")
        self.sub_math = Subject.objects.create(subject_name=f"Math_{suffix}")
        self.sub_physics = Subject.objects.create(subject_name=f"Physics_{suffix}")

        # Priorities for CSE: IT > Math > Physics
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_it, priority=1)
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_math, priority=2)
        SubjectPriority.objects.create(department=self.dept_cse, subject=self.sub_physics, priority=3)

        self.semester = "Fall 2026"
        self.exam = Exam.objects.create(
            department="CSE",
            semester=self.semester,
            total_marks=100,
            total_questions=50,
            duration_minutes=60,
        )
        self.config = AdmissionConfiguration.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            exam=self.exam,
            seat_limit=1,
            waiting_student_limit=2,
            threshold=50.0,
        )

        self.suffix = suffix

    def test_effective_choices_align_scheduled_and_central_results(self):
        """Scheduled results get one exam-department choice; Central keeps submitted choices."""
        scheduled_student = Students.objects.create(
            username=f"scheduled_choices_{self.suffix}",
            f_id=f"SCH-{self.suffix}",
            department_shortname="CSE",
            registration_semester=self.semester,
            department_choices=[],
        )
        scheduled_result = AdmissionResult.objects.create(
            exam=self.exam,
            student=scheduled_student,
            department=self.dept_cse,
            attended_exam=True,
        )
        self.assertEqual(
            get_effective_department_choices(result=scheduled_result),
            [{"department_id": self.dept_cse.id, "priority": 1}],
        )
        scheduled_data = AdmissionResultSerializer(scheduled_result).data
        self.assertEqual(
            scheduled_data["student_department_choices"],
            [
                {
                    "department_id": self.dept_cse.id,
                    "department_shortname": "CSE",
                    "priority": 1,
                }
            ],
        )
        scheduled_response = self.client.get(
            "/api/admission/results/",
            {
                "semester": self.semester,
                "exam_type": "SCHEDULED",
                "department_id": self.dept_cse.id,
                "search": scheduled_student.username,
                "is_admitted": "false",
            },
        )
        self.assertEqual(scheduled_response.status_code, status.HTTP_200_OK)
        self.assertEqual(scheduled_response.data["count"], 1)
        scheduled_row = scheduled_response.data["results"][0]
        self.assertEqual(scheduled_row["id"], scheduled_result.id)
        self.assertEqual(
            scheduled_row["student_department_choices"],
            [
                {
                    "department_id": self.dept_cse.id,
                    "department_shortname": "CSE",
                    "priority": 1,
                }
            ],
        )

        central_exam = Exam.objects.create(
            department="Central (FSIT)",
            semester=self.semester,
            total_marks=100,
            total_questions=50,
            duration_minutes=60,
            exam_type="CENTRAL",
        )
        central_student = Students.objects.create(
            username=f"central_choices_{self.suffix}",
            f_id=f"CTR-{self.suffix}",
            department_shortname="SWE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": self.dept_swe.id, "priority": 1},
                {"department_id": self.dept_cse.id, "priority": 2},
            ],
        )
        central_result = AdmissionResult.objects.create(
            exam=central_exam,
            student=central_student,
            department=self.dept_swe,
            attended_exam=True,
        )
        self.assertEqual(
            get_effective_department_choices(result=central_result),
            [
                {"department_id": self.dept_swe.id, "priority": 1},
                {"department_id": self.dept_cse.id, "priority": 2},
            ],
        )

    def test_multi_choice_choice1_full_choice2_allocated_and_waiting_for_choice1(self):
        """
        Required prompt example:
        Student has:
        Choice 1: CSE
        Choice 2: SWE
        Choice 3: MCT
        Student is eligible for all three.
        CSE has 0 seats available (full). SWE has 1 seat.
        Allocation must place student in SWE:
        - Allocated Department: SWE
        - Waiting List For: CSE
        - Consumes 1 seat in SWE, does not consume CSE seat.
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=0,  # Full!
            waiting_student_limit=5,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            min_threshold_mark=45.0,
            seat_limit=1,  # Available!
            waiting_student_limit=5,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_mct,
            semester=self.semester,
            min_threshold_mark=40.0,
            seat_limit=5,
            waiting_student_limit=5,
        )

        student = Students.objects.create(
            username=f"applicant_{self.suffix}",
            full_name="Multi Choice Applicant",
            f_id="1001",
            department_shortname="CSE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": self.dept_cse.id, "priority": 1},
                {"department_id": self.dept_swe.id, "priority": 2},
                {"department_id": self.dept_mct.id, "priority": 3},
            ],
        )

        result = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=75.0,
            attended_exam=True,
            subject_wise_marks={
                self.sub_it.subject_name: {"marks_obtained": 80.0},
                self.sub_math.subject_name: {"marks_obtained": 70.0},
            },
        )

        alloc_result = apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=0,
            waiting_student_limit=5,
        )
        self.assertTrue(alloc_result["success"])

        result.refresh_from_db()
        self.assertTrue(result.is_selected)
        self.assertEqual(result.result_status, "SELECTED")
        self.assertEqual(result.department_id, self.dept_swe.id)
        self.assertEqual(result.waiting_department_id, self.dept_cse.id)

        # Verify Serializer output matches required fields
        serializer = AdmissionResultSerializer(result)
        data = serializer.data

        self.assertEqual(data["allocated_department"], "SWE")
        self.assertEqual(data["waiting_for"], "CSE")
        self.assertIn("CSE", data["eligible_departments"])
        self.assertIn("SWE", data["eligible_departments"])
        self.assertIn("MCT", data["eligible_departments"])

        response = self.client.get(
            "/api/admission/results/",
            {"semester": self.semester, "result_status": "SELECTED"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        api_row = next(row for row in response.data["results"] if row["id"] == result.id)
        self.assertEqual(api_row["allocated_department"], "SWE")
        self.assertEqual(api_row["waiting_for"], "CSE")

    def test_lower_choice_waiting_respects_department_waiting_capacity(self):
        """Only merit-ranked candidates within the limit wait for Choice 1."""
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=0,
            waiting_student_limit=1,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            min_threshold_mark=45.0,
            seat_limit=2,
            waiting_student_limit=0,
        )

        results = []
        for index, score in enumerate((90.0, 80.0), start=1):
            student = Students.objects.create(
                username=f"capacity_{index}_{self.suffix}",
                full_name=f"Capacity Applicant {index}",
                f_id=str(4000 + index),
                department_shortname="CSE",
                registration_semester=self.semester,
                department_choices=[
                    {"department_id": self.dept_cse.id, "priority": 1},
                    {"department_id": self.dept_swe.id, "priority": 2},
                ],
            )
            results.append(
                AdmissionResult.objects.create(
                    exam=self.exam,
                    student=student,
                    department=self.dept_cse,
                    configuration=self.config,
                    weighted_total_marks=score,
                    attended_exam=True,
                )
            )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=0,
            waiting_student_limit=1,
        )

        for result in results:
            result.refresh_from_db()
            self.assertEqual(result.department_id, self.dept_swe.id)
            self.assertEqual(result.result_status, "SELECTED")

        self.assertEqual(results[0].waiting_department_id, self.dept_cse.id)
        self.assertIsNone(results[1].waiting_department_id)
        self.assertEqual(AdmissionResultSerializer(results[0]).data["waiting_for"], "CSE")
        self.assertIsNone(AdmissionResultSerializer(results[1]).data["waiting_for"])

    def test_legacy_string_choice_ids_allocate_and_serialize_correctly(self):
        """Imported JSON with string IDs behaves like serializer-created data."""
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=0,
            waiting_student_limit=1,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            min_threshold_mark=45.0,
            seat_limit=1,
            waiting_student_limit=1,
        )
        student = Students.objects.create(
            username=f"legacy_choices_{self.suffix}",
            full_name="Legacy Choice Applicant",
            f_id="4100",
            department_shortname="CSE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": str(self.dept_cse.id), "priority": "1"},
                {"department_id": str(self.dept_swe.id), "priority": "2"},
            ],
        )
        result = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=75.0,
            attended_exam=True,
        )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=0,
            waiting_student_limit=1,
        )

        result.refresh_from_db()
        data = AdmissionResultSerializer(result).data
        self.assertEqual(result.department_id, self.dept_swe.id)
        self.assertEqual(result.waiting_department_id, self.dept_cse.id)
        self.assertEqual(data["allocated_department"], "SWE")
        self.assertEqual(data["waiting_for"], "CSE")
        self.assertEqual(
            [choice["department_shortname"] for choice in data["student_department_choices"]],
            ["CSE", "SWE"],
        )

    def test_multi_choice_choice1_and_2_full_choice3_allocated(self):
        """
        Choice 1 (CSE): Full
        Choice 2 (SWE): Full
        Choice 3 (MCT): Available (1 seat)
        Student must be allocated to MCT, and waiting_for must be Choice 1 (CSE).
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=0,
            waiting_student_limit=5,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            min_threshold_mark=45.0,
            seat_limit=0,
            waiting_student_limit=5,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_mct,
            semester=self.semester,
            min_threshold_mark=40.0,
            seat_limit=1,
            waiting_student_limit=5,
        )

        student = Students.objects.create(
            username=f"applicant3_{self.suffix}",
            full_name="Third Choice Applicant",
            f_id="1002",
            department_shortname="CSE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": self.dept_cse.id, "priority": 1},
                {"department_id": self.dept_swe.id, "priority": 2},
                {"department_id": self.dept_mct.id, "priority": 3},
            ],
        )

        result = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=65.0,
            attended_exam=True,
        )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=0,
            waiting_student_limit=5,
        )

        result.refresh_from_db()
        self.assertTrue(result.is_selected)
        self.assertEqual(result.department_id, self.dept_mct.id)

        serializer = AdmissionResultSerializer(result)
        data = serializer.data
        self.assertEqual(data["allocated_department"], "MCT")
        self.assertEqual(data["waiting_for"], "CSE")

    def test_all_eligible_choices_full_waiting_list_assignment(self):
        """
        When all eligible choices have 0 seats available:
        Candidate is placed on waiting list for top choice (CSE).
        result_status = WAITING, is_selected = False.
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=0,
            waiting_student_limit=2,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            min_threshold_mark=45.0,
            seat_limit=0,
            waiting_student_limit=2,
        )

        student = Students.objects.create(
            username=f"waiting_stu_{self.suffix}",
            full_name="Waiting Applicant",
            f_id="1003",
            department_shortname="CSE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": self.dept_cse.id, "priority": 1},
                {"department_id": self.dept_swe.id, "priority": 2},
            ],
        )

        result = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=70.0,
            attended_exam=True,
        )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=0,
            waiting_student_limit=2,
        )

        result.refresh_from_db()
        self.assertFalse(result.is_selected)
        self.assertEqual(result.result_status, "WAITING")
        self.assertEqual(result.department_id, self.dept_cse.id)

        serializer = AdmissionResultSerializer(result)
        data = serializer.data
        self.assertIsNone(data["allocated_department"])
        self.assertEqual(data["waiting_for"], "CSE")

    def test_ineligible_for_all_choices_marked_rejected(self):
        """
        Attended applicant whose score is below threshold for all choices
        must be marked REJECTED and not placed on WAITING list.
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=10,
            waiting_student_limit=10,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            min_threshold_mark=45.0,
            seat_limit=10,
            waiting_student_limit=10,
        )

        student = Students.objects.create(
            username=f"below_thresh_{self.suffix}",
            full_name="Low Score Applicant",
            f_id="1004",
            department_shortname="CSE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": self.dept_cse.id, "priority": 1},
                {"department_id": self.dept_swe.id, "priority": 2},
            ],
        )

        result = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=35.0,  # Below both 50 and 45!
            attended_exam=True,
        )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=10,
            waiting_student_limit=10,
        )

        result.refresh_from_db()
        self.assertFalse(result.is_selected)
        self.assertEqual(result.result_status, "REJECTED")

        serializer = AdmissionResultSerializer(result)
        data = serializer.data
        self.assertIsNone(data["allocated_department"])
        self.assertIsNone(data["waiting_for"])
        self.assertEqual(data["eligible_departments"], [])

    def test_tiebreak_exact_order_total_priority_applicant_id(self):
        """
        Step 3 Tie-Breaking Priority:
        1. Total Score descending
        2. Subject Priority Mapping marks descending (IT > Math > Physics)
        3. Stable Applicant ID ascending (lower f_id ranks first)
        """
        priority_subjects = [self.sub_it.subject_name, self.sub_math.subject_name]

        class MockCandidate:
            def __init__(self, id, f_id, total, it_mark, math_mark):
                self.id = id
                self.student_id = id
                self.weighted_total_marks = total
                self.subject_wise_marks = {
                    priority_subjects[0]: {"marks_obtained": it_mark},
                    priority_subjects[1]: {"marks_obtained": math_mark},
                }
                # Attach mock student with f_id
                class MockStudent:
                    def __init__(self, f_id):
                        self.f_id = f_id
                self.student = MockStudent(f_id)

        # Case 1: Total score differs -> Total score wins regardless of subjects
        c1 = MockCandidate(1, "100", 80.0, 95.0, 95.0)
        c2 = MockCandidate(2, "200", 85.0, 50.0, 50.0)
        ordered1 = sorted([c1, c2], key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))
        self.assertEqual(ordered1[0].id, 2)  # 85.0 beats 80.0

        # Case 2: Total score equal -> Priority 1 (IT) mark wins
        c3 = MockCandidate(3, "100", 80.0, 90.0, 70.0)
        c4 = MockCandidate(4, "200", 80.0, 85.0, 95.0)
        ordered2 = sorted([c3, c4], key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))
        self.assertEqual(ordered2[0].id, 3)  # IT 90.0 beats IT 85.0

        # Case 3: Total score & IT tied -> Priority 2 (Math) mark wins
        c5 = MockCandidate(5, "100", 80.0, 90.0, 70.0)
        c6 = MockCandidate(6, "200", 80.0, 90.0, 85.0)
        ordered3 = sorted([c5, c6], key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))
        self.assertEqual(ordered3[0].id, 6)  # Math 85.0 beats Math 70.0

        # Case 4: Total & all subjects tied -> Lower Applicant ID wins
        c7 = MockCandidate(7, "050", 80.0, 90.0, 80.0)
        c8 = MockCandidate(8, "120", 80.0, 90.0, 80.0)
        ordered4 = sorted([c8, c7], key=lambda c: build_candidate_tiebreak_key(c, priority_subjects))
        self.assertEqual(ordered4[0].id, 7)  # f_id 050 beats 120

    def test_allocation_uses_subject_priority_mapping_for_equal_totals(self):
        """The mapped Priority 1 subject decides who receives the last seat."""
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=1,
            waiting_student_limit=1,
        )
        lower_applicant_id = Students.objects.create(
            username=f"lower_id_{self.suffix}",
            f_id="100",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        higher_priority_mark = Students.objects.create(
            username=f"higher_it_{self.suffix}",
            f_id="200",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        lower_result = AdmissionResult.objects.create(
            exam=self.exam,
            student=lower_applicant_id,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=80.0,
            attended_exam=True,
            subject_wise_marks={
                self.sub_it.subject_name: {"marks_obtained": 80.0},
                self.sub_math.subject_name: {"marks_obtained": 95.0},
            },
        )
        priority_result = AdmissionResult.objects.create(
            exam=self.exam,
            student=higher_priority_mark,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=80.0,
            attended_exam=True,
            subject_wise_marks={
                self.sub_it.subject_name: {"marks_obtained": 90.0},
                self.sub_math.subject_name: {"marks_obtained": 60.0},
            },
        )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=1,
            waiting_student_limit=1,
        )

        lower_result.refresh_from_db()
        priority_result.refresh_from_db()
        self.assertFalse(lower_result.is_selected)
        self.assertEqual(lower_result.result_status, "WAITING")
        self.assertTrue(priority_result.is_selected)
        self.assertEqual(priority_result.result_status, "SELECTED")

        response = self.client.get(
            "/api/admission/results/",
            {"semester": self.semester, "result_status": "SELECTED", "sort_by": "score"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["id"], priority_result.id)

    def test_central_exam_recalculation_resolves_mapped_faculty_department(self):
        """Central exams use FacultyDepartment rather than a nonexistent relation."""
        faculty = Faculty.objects.create(
            faculty_name=f"Faculty {self.suffix}",
            faculty_shortname=f"F_{self.suffix}",
        )
        FacultyDepartment.objects.create(
            faculty=faculty,
            department_ids=[self.dept_cse.id, self.dept_swe.id, self.dept_mct.id],
        )
        central_exam = Exam.objects.create(
            department=f"Central ({faculty.faculty_shortname})",
            semester=self.semester,
            total_marks=100,
            total_questions=50,
            duration_minutes=60,
            exam_type="CENTRAL",
            faculty_ref=faculty,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            exam=central_exam,
            min_threshold_mark=30.0,
            seat_limit=5,
            waiting_student_limit=0,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_swe,
            semester=self.semester,
            exam=central_exam,
            min_threshold_mark=50.0,
            seat_limit=5,
            waiting_student_limit=0,
        )
        DepartmentThreshold.objects.create(
            department=self.dept_mct,
            semester=self.semester,
            exam=central_exam,
            min_threshold_mark=25.0,
            seat_limit=5,
            waiting_student_limit=0,
        )
        student = Students.objects.create(
            username=f"central_{self.suffix}",
            f_id="5001",
            department_shortname="SWE",
            registration_semester=self.semester,
            department_choices=[
                {"department_id": self.dept_swe.id, "priority": 1},
                {"department_id": self.dept_mct.id, "priority": 2},
            ],
        )
        result = AdmissionResult.objects.create(
            exam=central_exam,
            student=student,
            department=self.dept_swe,
            weighted_total_marks=47.83,
            attended_exam=True,
        )

        calculation = calculate_admission_results(central_exam.id)

        self.assertTrue(calculation["success"])
        result.refresh_from_db()
        self.assertTrue(result.is_selected)
        self.assertEqual(result.result_status, "SELECTED")
        self.assertEqual(result.department_id, self.dept_mct.id)
        self.assertEqual(result.threshold_applied, 25.0)

    def test_protected_admitted_candidate_preserves_seat(self):
        """
        Admitted candidates hold their allocated seats permanently.
        They must be deducted from seat capacity before new merit selections,
        and must never be displaced or reallocated on recalculation.
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=1,  # Only 1 seat total!
            waiting_student_limit=5,
        )

        # Admitted student holds the 1 seat
        admitted_student = Students.objects.create(
            username=f"admitted_{self.suffix}",
            full_name="Admitted Student",
            f_id="1005",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        res_admitted = AdmissionResult.objects.create(
            exam=self.exam,
            student=admitted_student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=70.0,
            attended_exam=True,
            is_selected=True,
            is_admitted=True,
            result_status="SELECTED",
        )

        # New applicant with higher total marks (90.0 > 70.0)
        new_student = Students.objects.create(
            username=f"new_applicant_{self.suffix}",
            full_name="New Top Applicant",
            f_id="1006",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        res_new = AdmissionResult.objects.create(
            exam=self.exam,
            student=new_student,
            department=self.dept_cse,
            configuration=self.config,
            weighted_total_marks=90.0,
            attended_exam=True,
        )

        apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=1,
            waiting_student_limit=5,
        )

        res_admitted.refresh_from_db()
        res_new.refresh_from_db()

        # Admitted student STILL holds their seat
        self.assertTrue(res_admitted.is_selected)
        self.assertTrue(res_admitted.is_admitted)
        self.assertEqual(res_admitted.result_status, "SELECTED")

        # New applicant cannot displace admitted student; gets WAITING instead
        self.assertFalse(res_new.is_selected)
        self.assertEqual(res_new.result_status, "WAITING")

    def test_allocation_idempotence(self):
        """
        Re-running allocation multiple times on unchanged inputs
        produces identical outcomes and does not create duplicate entries.
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=2,
            waiting_student_limit=2,
        )

        s1 = Students.objects.create(
            username=f"idem1_{self.suffix}",
            f_id="2001",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        s2 = Students.objects.create(
            username=f"idem2_{self.suffix}",
            f_id="2002",
            department_shortname="CSE",
            registration_semester=self.semester,
        )

        r1 = AdmissionResult.objects.create(
            exam=self.exam, student=s1, department=self.dept_cse,
            weighted_total_marks=80.0, attended_exam=True,
        )
        r2 = AdmissionResult.objects.create(
            exam=self.exam, student=s2, department=self.dept_cse,
            weighted_total_marks=70.0, attended_exam=True,
        )

        # Run 1
        run1 = apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=2,
            waiting_student_limit=2,
        )
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertTrue(r1.is_selected)
        self.assertTrue(r2.is_selected)

        # Run 2
        run2 = apply_semester_result_statuses(
            department=self.dept_cse,
            semester=self.semester,
            threshold_value=50.0,
            seat_limit=2,
            waiting_student_limit=2,
        )
        r1.refresh_from_db()
        r2.refresh_from_db()
        self.assertEqual(AdmissionResult.objects.filter(exam=self.exam).count(), 2)

    def test_get_admission_results_semester_only_filter_does_not_crash(self):
        """
        Verify that querying /api/admission/results/ with semester but without department_id
        resolves successfully without crashing on invalid reverse lookup fields.
        """
        DepartmentThreshold.objects.create(
            department=self.dept_cse,
            semester=self.semester,
            min_threshold_mark=50.0,
            seat_limit=10,
            waiting_student_limit=5,
        )

        response = self.client.get(
            "/api/admission/results/",
            {"semester": self.semester, "result_status": "SELECTED", "page": 1},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("success"))
        self.assertIn("results", response.data)
        self.assertIn("summary", response.data)

    def test_results_support_multi_department_and_faculty_filters(self):
        """The results board can query several mapped departments as one cohort."""
        students_and_departments = []
        for index, department in enumerate(
            (self.dept_cse, self.dept_swe, self.dept_mct), start=1
        ):
            student = Students.objects.create(
                username=f"scope_{index}_{self.suffix}",
                f_id=f"SCOPE-{index}",
                department_shortname=department.department_shortname,
                registration_semester=self.semester,
            )
            result = AdmissionResult.objects.create(
                exam=self.exam,
                student=student,
                department=department,
                weighted_total_marks=80.0 - index,
                attended_exam=True,
                is_selected=True,
                result_status="SELECTED",
            )
            students_and_departments.append((result, department))

        expected_ids = {
            students_and_departments[1][0].id,
            students_and_departments[2][0].id,
        }
        multi_response = self.client.get(
            "/api/admission/results/",
            {
                "department_ids": f"{self.dept_swe.id},{self.dept_mct.id}",
                "result_status": "SELECTED",
            },
        )
        self.assertEqual(multi_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {row["id"] for row in multi_response.data["results"]},
            expected_ids,
        )
        multi_semester_response = self.client.get(
            "/api/admission/semester-options/",
            {"department_ids": f"{self.dept_swe.id},{self.dept_mct.id}"},
        )
        self.assertEqual(multi_semester_response.status_code, status.HTTP_200_OK)
        self.assertIn(self.semester, multi_semester_response.data["semesters"])

        faculty = Faculty.objects.create(
            faculty_name=f"Results Faculty {self.suffix}",
            faculty_shortname=f"RF_{self.suffix}",
        )
        FacultyDepartment.objects.create(
            faculty=faculty,
            department_ids=[self.dept_swe.id, self.dept_mct.id],
        )
        faculty_response = self.client.get(
            "/api/admission/results/",
            {"faculty_id": faculty.id, "result_status": "SELECTED"},
        )
        self.assertEqual(faculty_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {row["id"] for row in faculty_response.data["results"]},
            expected_ids,
        )
        faculty_semester_response = self.client.get(
            "/api/admission/semester-options/",
            {"faculty_id": faculty.id},
        )
        self.assertEqual(faculty_semester_response.status_code, status.HTTP_200_OK)
        self.assertIn(self.semester, faculty_semester_response.data["semesters"])

        second_faculty = Faculty.objects.create(
            faculty_name=f"Second Results Faculty {self.suffix}",
            faculty_shortname=f"RF2_{self.suffix}",
        )
        FacultyDepartment.objects.create(
            faculty=second_faculty,
            department_ids=[self.dept_cse.id],
        )
        multi_faculty_response = self.client.get(
            "/api/admission/results/",
            {
                "faculty_ids": f"{faculty.id},{second_faculty.id}",
                "result_status": "SELECTED",
            },
        )
        self.assertEqual(multi_faculty_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {row["id"] for row in multi_faculty_response.data["results"]},
            {result.id for result, _department in students_and_departments},
        )
        multi_faculty_semesters = self.client.get(
            "/api/admission/semester-options/",
            {"faculty_ids": f"{faculty.id},{second_faculty.id}"},
        )
        self.assertEqual(multi_faculty_semesters.status_code, status.HTTP_200_OK)
        self.assertIn(self.semester, multi_faculty_semesters.data["semesters"])

        scoped_role = Role.objects.create(role_name=f"results_scope_{self.suffix}")
        faculty_user = User.objects.create(
            username=f"faculty_results_{self.suffix}",
            email=f"faculty_results_{self.suffix}@example.com",
            password=make_password("Secret123!"),
            role=scoped_role,
            faculty=faculty,
            access_type="FACULTY",
        )
        faculty_tokens = get_tokens_for_user(faculty_user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {faculty_tokens['access']}"
        )
        scoped_faculty_response = self.client.get(
            "/api/admission/results/",
            {"result_status": "SELECTED"},
        )
        self.assertEqual(scoped_faculty_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {row["id"] for row in scoped_faculty_response.data["results"]},
            expected_ids,
        )

        department_user = User.objects.create(
            username=f"department_results_{self.suffix}",
            email=f"department_results_{self.suffix}@example.com",
            password=make_password("Secret123!"),
            role=scoped_role,
            department=self.dept_cse,
            access_type="DEPARTMENT",
        )
        department_tokens = get_tokens_for_user(department_user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {department_tokens['access']}"
        )
        unauthorized_multi_response = self.client.get(
            "/api/admission/results/",
            {
                "department_ids": f"{self.dept_swe.id},{self.dept_mct.id}",
                "result_status": "SELECTED",
            },
        )
        self.assertEqual(unauthorized_multi_response.status_code, status.HTTP_200_OK)
        self.assertEqual(unauthorized_multi_response.data["count"], 0)

    def test_results_exam_type_filter_updates_filtered_summary(self):
        """Exam type filtering supports explicit and legacy Central exams."""
        central_exam = Exam.objects.create(
            department="CSE",
            semester=self.semester,
            total_marks=100,
            total_questions=50,
            duration_minutes=60,
            exam_type="CENTRAL",
        )
        legacy_central_exam = Exam.objects.create(
            department="Central (FSIT)",
            semester=self.semester,
            total_marks=100,
            total_questions=50,
            duration_minutes=60,
            # Legacy rows received the model default even though their label
            # identifies them as Central.
            exam_type="SCHEDULED",
        )
        created_results = []
        for username, exam in (
            (f"scheduled_scope_{self.suffix}", self.exam),
            (f"central_alpha_{self.suffix}", central_exam),
            (f"central_beta_{self.suffix}", central_exam),
            (f"legacy_central_{self.suffix}", legacy_central_exam),
        ):
            student = Students.objects.create(
                username=username,
                full_name=username.replace("_", " ").title(),
                f_id=f"TYPE-{len(created_results) + 1}",
                department_shortname="CSE",
                registration_semester=self.semester,
            )
            created_results.append(
                AdmissionResult.objects.create(
                    exam=exam,
                    student=student,
                    department=self.dept_cse,
                    weighted_total_marks=75.0,
                    attended_exam=True,
                    is_selected=True,
                    result_status="SELECTED",
                )
            )

        central_response = self.client.get(
            "/api/admission/results/",
            {"exam_type": "CENTRAL", "result_status": "SELECTED"},
        )
        self.assertEqual(central_response.status_code, status.HTTP_200_OK)
        self.assertEqual(central_response.data["count"], 3)
        self.assertEqual(central_response.data["summary"]["SELECTED"], 3)
        self.assertNotIn(
            created_results[0].id,
            {row["id"] for row in central_response.data["results"]},
        )
        legacy_row = next(
            row
            for row in central_response.data["results"]
            if row["id"] == created_results[3].id
        )
        self.assertEqual(legacy_row["exam_details"]["exam_type"], "CENTRAL")

        scheduled_response = self.client.get(
            "/api/admission/results/",
            {"exam_type": "SCHEDULED", "result_status": "SELECTED"},
        )
        self.assertEqual(scheduled_response.status_code, status.HTTP_200_OK)
        self.assertEqual(scheduled_response.data["count"], 1)
        self.assertEqual(scheduled_response.data["summary"]["SELECTED"], 1)
        self.assertEqual(
            scheduled_response.data["results"][0]["id"],
            created_results[0].id,
        )
        self.assertEqual(
            scheduled_response.data["results"][0]["exam_details"]["exam_type"],
            "SCHEDULED",
        )

        searched_response = self.client.get(
            "/api/admission/results/",
            {
                "exam_type": "CENTRAL",
                "search": f"central_alpha_{self.suffix}",
                "result_status": "SELECTED",
            },
        )
        self.assertEqual(searched_response.status_code, status.HTTP_200_OK)
        self.assertEqual(searched_response.data["count"], 1)
        self.assertEqual(searched_response.data["summary"]["SELECTED"], 1)
        self.assertEqual(searched_response.data["results"][0]["id"], created_results[1].id)

    def test_get_admission_results_accepted_tab_returns_admitted_students(self):
        """
        Verify that querying /api/admission/results/ with result_status=ACCEPTED
        returns candidates with is_admitted=True.
        """
        student = Students.objects.create(
            username=f"admitted_{self.suffix}",
            f_id="3001",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        res = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            weighted_total_marks=85.0,
            attended_exam=True,
            is_selected=True,
            is_admitted=True,
            result_status="SELECTED",
        )

        response = self.client.get(
            "/api/admission/results/",
            {"semester": self.semester, "result_status": "ACCEPTED", "page": 1},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get("success"))
        returned_ids = [r["id"] for r in response.data.get("results", [])]
        self.assertIn(res.id, returned_ids)
        sample = next(r for r in response.data["results"] if r["id"] == res.id)
        self.assertTrue(sample.get("is_admitted"))
        self.assertEqual(sample.get("allocated_department"), "CSE")

    def test_all_results_includes_unselected_student_without_allocation(self):
        """The pre-admission board includes rejected rows but excludes admitted rows."""
        search_prefix = f"all_results_board_{self.suffix}"
        username = f"{search_prefix}_rejected"
        student = Students.objects.create(
            username=username,
            f_id=f"UNSELECTED-{self.suffix}",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        rejected_result = AdmissionResult.objects.create(
            exam=self.exam,
            student=student,
            department=self.dept_cse,
            weighted_total_marks=35.0,
            attended_exam=True,
            is_selected=False,
            is_admitted=False,
            result_status="REJECTED",
        )
        admitted_student = Students.objects.create(
            username=f"{search_prefix}_admitted",
            f_id=f"ADMITTED-{self.suffix}",
            department_shortname="CSE",
            registration_semester=self.semester,
        )
        admitted_result = AdmissionResult.objects.create(
            exam=self.exam,
            student=admitted_student,
            department=self.dept_cse,
            weighted_total_marks=85.0,
            attended_exam=True,
            is_selected=True,
            is_admitted=True,
            result_status="SELECTED",
        )

        response = self.client.get(
            "/api/admission/results/",
            {"search": search_prefix, "is_admitted": "false", "page": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = next(
            row
            for row in response.data.get("results", [])
            if row["id"] == rejected_result.id
        )
        self.assertEqual(returned["result_status"], "REJECTED")
        self.assertFalse(returned["is_selected"])
        self.assertIsNone(returned["allocated_department"])
        self.assertNotIn(
            admitted_result.id,
            {row["id"] for row in response.data.get("results", [])},
        )
        self.assertEqual(response.data["filters_applied"]["is_admitted"], "false")

