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
    ScrappedQuestion,
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
        """Department inherits subjects from parent faculty"""
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

    def test_subject_faculty_direct_api_crud_and_deduplication(self):
        """Verify direct Subject-Faculty mapping creation, deduplication, and retrieval via API"""
        sub1 = Subject.objects.create(subject_name=f"Calculus {uuid4().hex[:4]}")
        sub2 = Subject.objects.create(subject_name=f"English {uuid4().hex[:4]}")

        # 1. Create mapping with duplicate subject ID in payload to verify deduplication
        payload = {
            "faculty": self.faculty_fsit.id,
            "subject_ids": [sub1.id, sub2.id, sub1.id],
        }
        response = self.client.post("/api/subject-faculties/create/", payload, format="json")
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED])
        data = response.data["data"]
        self.assertEqual(data["faculty_id"], self.faculty_fsit.id)
        # Deduplicated
        self.assertEqual(len(data["subject_ids"]), 2)
        self.assertIn(sub1.id, data["subject_ids"])
        self.assertIn(sub2.id, data["subject_ids"])
        mapping_id = data["id"]

        # 2. Retrieve mapping by ID
        get_res = self.client.get(f"/api/subject-faculties/{mapping_id}/")
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.data["data"]["faculty_id"], self.faculty_fsit.id)

        # 3. Retrieve by faculty ID
        fac_res = self.client.get(f"/api/subject-faculties/faculty/{self.faculty_fsit.id}/")
        self.assertEqual(fac_res.status_code, status.HTTP_200_OK)
        self.assertEqual(fac_res.data["data"]["id"], mapping_id)

        # 4. Update mapping
        update_payload = {
            "faculty": self.faculty_fsit.id,
            "subject_ids": [sub2.id],
        }
        upd_res = self.client.put(f"/api/subject-faculties/{mapping_id}/update/", update_payload, format="json")
        self.assertEqual(upd_res.status_code, status.HTTP_200_OK)
        self.assertEqual(upd_res.data["data"]["subject_ids"], [sub2.id])

    def test_faculty_isolation_and_cross_faculty_sharing(self):
        """Verify multiple departments under same faculty inherit subjects, and faculties remain isolated"""
        sub_math = Subject.objects.create(subject_name=f"Common Math {uuid4().hex[:4]}")
        sub_cs = Subject.objects.create(subject_name=f"Computer Science {uuid4().hex[:4]}")
        sub_circuit = Subject.objects.create(subject_name=f"Electric Circuits {uuid4().hex[:4]}")

        # Map FSIT -> Math and Computer Science
        SubjectFaculty.objects.create(
            faculty=self.faculty_fsit,
            subject_ids=[sub_math.id, sub_cs.id],
        )

        # Map FE -> Common Math and Electric Circuits (sub_math is shared across faculties!)
        SubjectFaculty.objects.create(
            faculty=self.faculty_fe,
            subject_ids=[sub_math.id, sub_circuit.id],
        )

        # 1. Both CSE and SWE under FSIT must inherit sub_math and sub_cs
        cse_res = self.client.get(f"/api/subject-departments/department/{self.dept_cse.id}/")
        self.assertEqual(cse_res.status_code, status.HTTP_200_OK)
        cse_sub_ids = cse_res.data["data"]["subject_ids"]
        self.assertIn(sub_math.id, cse_sub_ids)
        self.assertIn(sub_cs.id, cse_sub_ids)
        self.assertNotIn(sub_circuit.id, cse_sub_ids)

        swe_res = self.client.get(f"/api/subject-departments/department/{self.dept_swe.id}/")
        self.assertEqual(swe_res.status_code, status.HTTP_200_OK)
        swe_sub_ids = swe_res.data["data"]["subject_ids"]
        self.assertIn(sub_math.id, swe_sub_ids)
        self.assertIn(sub_cs.id, swe_sub_ids)
        self.assertNotIn(sub_circuit.id, swe_sub_ids)

        # 2. EEE under FE must inherit sub_math and sub_circuit, but NOT sub_cs
        eee_res = self.client.get(f"/api/subject-departments/department/{self.dept_eee.id}/")
        self.assertEqual(eee_res.status_code, status.HTTP_200_OK)
        eee_sub_ids = eee_res.data["data"]["subject_ids"]
        self.assertIn(sub_math.id, eee_sub_ids)
        self.assertIn(sub_circuit.id, eee_sub_ids)
        self.assertNotIn(sub_cs.id, eee_sub_ids)

    def test_authoritative_resolution_bypasses_stale_department_mapping(self):
        """Verify parent faculty mapping authoritatively overrides stale department mapping"""
        from ..models import SubjectDepartment
        sub_old = Subject.objects.create(subject_name=f"Old Sub {uuid4().hex[:4]}")
        sub_new1 = Subject.objects.create(subject_name=f"New Sub 1 {uuid4().hex[:4]}")
        sub_new2 = Subject.objects.create(subject_name=f"New Sub 2 {uuid4().hex[:4]}")

        # Legacy department-level record with old subject
        SubjectDepartment.objects.create(
            department=self.dept_cse,
            subject_ids=[sub_old.id],
        )

        # Authoritative faculty mapping with new subjects
        SubjectFaculty.objects.create(
            faculty=self.faculty_fsit,
            subject_ids=[sub_new1.id, sub_new2.id],
        )

        # Department endpoint must resolve from parent faculty authoritatively
        response = self.client.get(f"/api/subject-departments/department/{self.dept_cse.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resolved_ids = response.data["data"]["subject_ids"]
        self.assertIn(sub_new1.id, resolved_ids)
        self.assertIn(sub_new2.id, resolved_ids)
        self.assertNotIn(sub_old.id, resolved_ids)

    def test_subject_deletion_purges_from_faculty_mapping(self):
        """Deleting a subject cleans it from SubjectFaculty mappings preventing dangling IDs"""
        sub_del = Subject.objects.create(subject_name=f"To Delete {uuid4().hex[:4]}")
        sub_keep = Subject.objects.create(subject_name=f"To Keep {uuid4().hex[:4]}")

        sf = SubjectFaculty.objects.create(
            faculty=self.faculty_fsit,
            subject_ids=[sub_del.id, sub_keep.id],
        )

        # Delete subject
        del_res = self.client.delete(f"/api/subjects/{sub_del.id}/delete/")
        self.assertEqual(del_res.status_code, status.HTTP_200_OK)

        sf.refresh_from_db()
        self.assertNotIn(sub_del.id, sf.subject_ids)
        self.assertIn(sub_keep.id, sf.subject_ids)

    def test_subject_priority_displays_faculty_inherited_subjects(self):
        """Subject priority mapping API marks faculty-inherited subjects as is_department_subject"""
        sub_pri = Subject.objects.create(subject_name=f"Priority Sub {uuid4().hex[:4]}")
        SubjectFaculty.objects.create(
            faculty=self.faculty_fsit,
            subject_ids=[sub_pri.id],
        )

        response = self.client.get(f"/api/subject-priorities/department/{self.dept_cse.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        avail = response.data["data"]["available_subjects"]
        pri_sub_item = next((s for s in avail if s["id"] == sub_pri.id), None)
        self.assertIsNotNone(pri_sub_item)
        self.assertTrue(pri_sub_item["is_department_subject"])

    def _create_question(self, subject, dept_shortname, text="Sample Question", marks=5):
        return ScrappedQuestion.objects.create(
            subject=subject,
            questions={"english": text, "both": f"{text} / বাংলা"},
            type="option",
            options={
                "english": {"A": "Choice A", "B": "Choice B"},
                "both": {"A": "Choice A", "B": "Choice B"},
            },
            answer={"english": "A", "both": "A"},
            marks=marks,
            semester="Spring 2026",
            department_shortname=dept_shortname,
        )

    def test_central_exam_generation_retrieves_questions_across_faculty_departments(self):
        """Test A: FSIT exam retrieves questions from CSE and SWE but strictly excludes outside FE (EEE)"""
        sub_name = f"Physics_{uuid4().hex[:6]}"
        q_cse = self._create_question(sub_name, "CSE", "CSE Physics Q", marks=5)
        q_swe = self._create_question(sub_name, "SWE", "SWE Physics Q", marks=5)
        q_eee = self._create_question(sub_name, "EEE", "EEE Physics Q", marks=5)

        # Generate Central exam for FSIT (which contains CSE and SWE)
        response = self.client.post(
            "/api/exams/generate/",
            {
                "exam_type": "CENTRAL",
                "faculty_id": self.faculty_fsit.id,
                "semester": "Spring 2026",
                "duration_minutes": 60,
                "language": "english",
                "faculty": "FSIT",
                "subjects": [{"subject": sub_name, "marks": 10}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_questions = response.data["data"]["questions"]
        returned_ids = [q["id"] for q in returned_questions]
        
        # Must include FSIT department questions
        self.assertIn(q_cse.id, returned_ids)
        self.assertIn(q_swe.id, returned_ids)
        # Must strictly exclude outside faculty questions
        self.assertNotIn(q_eee.id, returned_ids)

    def test_central_exam_generation_faculty_isolation(self):
        """Test B: FE exam retrieves only EEE questions and strictly excludes FSIT (CSE/SWE) questions"""
        sub_name = f"Math_{uuid4().hex[:6]}"
        q_cse = self._create_question(sub_name, "CSE", "CSE Math Q", marks=5)
        q_eee = self._create_question(sub_name, "EEE", "EEE Math Q", marks=5)

        # Generate Central exam for FE (which only contains EEE)
        response = self.client.post(
            "/api/exams/generate/",
            {
                "exam_type": "CENTRAL",
                "faculty_id": self.faculty_fe.id,
                "semester": "Spring 2026",
                "duration_minutes": 60,
                "language": "english",
                "faculty": "FE",
                "subjects": [{"subject": sub_name, "marks": 5}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_questions = response.data["data"]["questions"]
        returned_ids = [q["id"] for q in returned_questions]

        self.assertIn(q_eee.id, returned_ids)
        self.assertNotIn(q_cse.id, returned_ids)

    def test_central_exam_generation_empty_faculty_returns_404(self):
        """Test C: Faculty with no eligible questions returns 404 without silent fallback to all questions"""
        suffix = uuid4().hex[:6]
        empty_faculty = Faculty.objects.create(
            faculty_name=f"Empty Faculty {suffix}",
            faculty_shortname=f"EF_{suffix}",
        )
        empty_dept = Department.objects.create(
            department_name=f"Empty Dept {suffix}",
            department_shortname=f"ED_{suffix}",
        )
        FacultyDepartment.objects.create(
            faculty=empty_faculty,
            department_ids=[empty_dept.id],
        )

        sub_name = f"AnySubject_{uuid4().hex[:6]}"
        # Existing question exists for another faculty
        self._create_question(sub_name, "CSE", "Other Q", marks=5)

        response = self.client.post(
            "/api/exams/generate/",
            {
                "exam_type": "CENTRAL",
                "faculty_id": empty_faculty.id,
                "semester": "Spring 2026",
                "duration_minutes": 60,
                "language": "english",
                "faculty": empty_faculty.faculty_shortname,
                "subjects": [{"subject": sub_name, "marks": 5}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("No questions available", response.data["message"])

    def test_central_exam_regenerate_question_respects_faculty_scope(self):
        """Test D: Single question regeneration for Central exam only picks replacement from faculty scope"""
        sub_name = f"GK_{uuid4().hex[:6]}"
        q_current = self._create_question(sub_name, "CSE", "Current GK Q", marks=5)
        q_fsit_rep = self._create_question(sub_name, "SWE", "SWE GK Replacement", marks=5)
        q_fe_outside = self._create_question(sub_name, "EEE", "EEE GK Outside", marks=5)

        response = self.client.post(
            "/api/exams/regenerate-question/",
            {
                "exam_type": "CENTRAL",
                "faculty_id": self.faculty_fsit.id,
                "subject": sub_name,
                "marks": 5,
                "language": "english",
                "exclude_question_ids": [q_current.id],
                "exclude_question_texts": ["Current GK Q"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        question = response.data["data"]["question"]
        self.assertEqual(question["id"], q_fsit_rep.id)
        self.assertNotEqual(question["id"], q_fe_outside.id)

    def test_central_exam_save_rejects_outside_faculty_questions(self):
        """Test E: API security rejects saving Central exam containing outside faculty question"""
        sub_name = f"SecuritySub_{uuid4().hex[:6]}"
        q_fsit = self._create_question(sub_name, "CSE", "Valid FSIT Q", marks=5)
        q_fe = self._create_question(sub_name, "EEE", "Outside FE Q", marks=5)

        # Attempt to save FSIT Central exam containing q_fe
        response = self.client.post(
            "/api/exams/save-generated/",
            {
                "exam_type": "CENTRAL",
                "faculty_id": self.faculty_fsit.id,
                "faculty": "FSIT",
                "department": "Central (FSIT)",
                "semester": "Spring 2026",
                "duration_minutes": 60,
                "total_questions": 2,
                "total_marks": 10,
                "language": "English",
                "questions": [
                    {
                        "id": q_fsit.id,
                        "subject": sub_name,
                        "questions": "Valid FSIT Q",
                        "type": "option",
                        "marks": 5,
                        "department_shortname": "CSE",
                    },
                    {
                        "id": q_fe.id,
                        "subject": sub_name,
                        "questions": "Outside FE Q",
                        "type": "option",
                        "marks": 5,
                        "department_shortname": "EEE",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("outside", response.data["message"].lower())

    def test_central_exam_save_success_and_preserves_question_departments(self):
        """Test F: Valid Central exam saves successfully with faculty association and per-question departments"""
        sub_name = f"SaveSub_{uuid4().hex[:6]}"
        q_cse = self._create_question(sub_name, "CSE", "CSE Q", marks=5)
        q_swe = self._create_question(sub_name, "SWE", "SWE Q", marks=5)

        response = self.client.post(
            "/api/exams/save-generated/",
            {
                "exam_type": "CENTRAL",
                "faculty_id": self.faculty_fsit.id,
                "faculty": "FSIT",
                "department": "Central (FSIT)",
                "semester": "Spring 2026",
                "duration_minutes": 60,
                "total_questions": 2,
                "total_marks": 10,
                "language": "English",
                "questions": [
                    {
                        "id": q_cse.id,
                        "subject": sub_name,
                        "questions": "CSE Q",
                        "type": "option",
                        "marks": 5,
                        "department_shortname": "CSE",
                    },
                    {
                        "id": q_swe.id,
                        "subject": sub_name,
                        "questions": "SWE Q",
                        "type": "option",
                        "marks": 5,
                        "department_shortname": "SWE",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        exam_id = response.data["data"]["exam_id"]
        saved_exam = Exam.objects.get(id=exam_id)
        self.assertEqual(saved_exam.exam_type, "CENTRAL")
        self.assertEqual(saved_exam.faculty_ref, self.faculty_fsit)
        self.assertEqual(saved_exam.faculty, "FSIT")

        exam_questions = saved_exam.exam_questions.all()
        self.assertEqual(exam_questions.count(), 2)
        eq_depts = set(exam_questions.values_list("department_shortname", flat=True))
        self.assertEqual(eq_depts, {"CSE", "SWE"})

    def test_scheduled_exam_department_isolation_preserved(self):
        """Test G: Scheduled exam creation preserves department-specific scoping"""
        sub_name = f"SchedSub_{uuid4().hex[:6]}"
        q_cse = self._create_question(sub_name, "CSE", "CSE Only Q", marks=5)
        q_swe = self._create_question(sub_name, "SWE", "SWE Other Q", marks=5)

        # Generate Scheduled exam for CSE
        response = self.client.post(
            "/api/exams/generate/",
            {
                "exam_type": "SCHEDULED",
                "department_id": self.dept_cse.id,
                "semester": "Spring 2026",
                "duration_minutes": 60,
                "language": "english",
                "subjects": [{"subject": sub_name, "marks": 5}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_questions = response.data["data"]["questions"]
        returned_ids = [q["id"] for q in returned_questions]

        self.assertIn(q_cse.id, returned_ids)
        self.assertNotIn(q_swe.id, returned_ids)

