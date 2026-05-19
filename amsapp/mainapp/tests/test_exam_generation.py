from uuid import uuid4

from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import BlocklistQuestion, Department, Role, ScrappedQuestion, User
from ..tokens import get_tokens_for_user


class RowLevelQuestionRegenerationTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        self.role = Role.objects.create(role_name=f"Exam Admin {suffix}")
        self.department = Department.objects.create(
            department_name=f"Computer Science {suffix}",
            department_shortname="CSE",
        )
        self.user = User.objects.create(
            username=f"exam-admin-{suffix}",
            email=f"exam-admin-{suffix}@test.com",
            password=make_password("admin123"),
            role=self.role,
            department=self.department,
        )
        tokens = get_tokens_for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def create_question(self, text, *, subject="Mathematics", marks=5):
        return ScrappedQuestion.objects.create(
            subject=subject,
            questions={"english": text, "both": f"{text} / বাংলা"},
            type="option",
            options={
                "english": {"A": "One", "B": "Two"},
                "both": {"A": "One / এক", "B": "Two / দুই"},
            },
            answer={"english": "A", "both": "A"},
            marks=marks,
            semester="Spring 2026",
            department_shortname="CSE",
        )

    def test_regenerate_question_uses_same_subject_marks_and_excludes_duplicates(self):
        current = self.create_question("Current question")
        duplicate_text = self.create_question("Duplicate displayed text")
        blocked = self.create_question("Blocked question")
        replacement = self.create_question("Replacement question")
        self.create_question("Different marks question", marks=10)
        self.create_question("Different subject question", subject="Physics")

        BlocklistQuestion.objects.create(
            subject=blocked.subject,
            questions=blocked.questions,
            type=blocked.type,
            text=blocked.text,
            options=blocked.options,
            answer=blocked.answer,
            marks=blocked.marks,
            semester=blocked.semester,
            department_shortname=blocked.department_shortname,
            original_question_id=blocked.id,
            remarks="Do not use",
            creator=self.user,
        )

        response = self.client.post(
            "/api/exams/regenerate-question/",
            {
                "department_id": self.department.id,
                "subject": "Mathematics",
                "marks": 5,
                "language": "english",
                "exclude_question_ids": [current.id],
                "exclude_question_texts": ["Duplicate displayed text"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        question = response.data["data"]["question"]
        self.assertEqual(question["id"], replacement.id)
        self.assertEqual(question["subject"], "Mathematics")
        self.assertEqual(question["marks"], 5)
        self.assertEqual(question["questions"], "Replacement question")

    def test_regenerate_question_returns_404_when_no_replacement_exists(self):
        current = self.create_question("Only question", subject="English", marks=3)

        response = self.client.post(
            "/api/exams/regenerate-question/",
            {
                "department_id": self.department.id,
                "subject": "English",
                "marks": 3,
                "language": "english",
                "exclude_question_ids": [current.id],
                "exclude_question_texts": ["Only question"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])
        self.assertEqual(
            response.data["message"],
            "No replacement question available for this subject and marks.",
        )
