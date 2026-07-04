from io import BytesIO
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.test import TestCase
from docx import Document
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import Role, ScrappedQuestion, User
from ..tokens import get_tokens_for_user
from ..utils.question_ingestion import ingest_scraped_question_entries, validate_scraped_question_item
from ..views.demo_scrapper import parse_docx_fileobj


class DocxScraperParsingTests(TestCase):
    def _build_docx(self) -> BytesIO:
        document = Document()
        document.add_paragraph("Subject: Math")
        document.add_paragraph("Spring 2026")
        document.add_paragraph("Department: CSE")
        document.add_paragraph("1. What is 2 + 2?")
        document.add_paragraph("(ক) 3")
        document.add_paragraph("(খ) 4")
        document.add_paragraph("(গ) 5")
        document.add_paragraph("(ঘ) 6")
        document.add_paragraph("Answer:")
        document.add_paragraph("1 খ")

        buffer = BytesIO()
        document.save(buffer)
        buffer.seek(0)
        return buffer

    def test_parse_docx_fileobj_preserves_question_and_answer_structure(self):
        parsed = parse_docx_fileobj(self._build_docx(), "math-cse.docx")

        self.assertEqual(len(parsed), 1)
        item = parsed[0]
        self.assertEqual(item["subject"], "Math")
        self.assertEqual(item["semester"], "Spring 2026")
        self.assertEqual(item["department"], "CSE")
        self.assertEqual(item["question_both"], "What is 2 + 2?")
        self.assertEqual(item["options"]["both"]["খ"], "4")
        self.assertEqual(item["answer"]["both"], ["খ"])
        self.assertEqual(item["answer"]["english"], ["B"])


class ScrappedQuestionIngestionTests(TestCase):
    def test_validate_scraped_question_item_rejects_blankish_option_question(self):
        normalized, issues = validate_scraped_question_item(
            {
                "subject": "Math",
                "question_bangla": "বিন্দুর মধ্যবিন্দু কত?",
                "question_english": "What is the midpoint?",
                "question_both": "বিন্দুর মধ্যবিন্দু কত? (What is the midpoint?)",
                "options": {
                    "both": {"ক": ",", "খ": ",", "গ": "(x₁+y₁, x₂+y₂)", "ঘ": ","},
                    "english": {"A": ",", "B": ",", "C": "(x1+y1, x2+y2)", "D": ","},
                },
                "answer": {"both": ["ক"], "english": ["A"]},
                "semester": "Spring 2026",
                "department": "CSE",
            }
        )

        self.assertEqual(normalized["type"], "option")
        self.assertIn("Bangla option set must contain 4 real options.", issues)
        self.assertIn("English option set must contain 4 real options.", issues)
        self.assertIn("Bangla answer key does not map to a real option.", issues)
        self.assertIn("English answer key does not map to a real option.", issues)

    def test_ingest_scraped_question_entries_blocks_invalid_rows(self):
        summary = ingest_scraped_question_entries(
            [
                {
                    "filename": "broken-math.docx",
                    "data": [
                        {
                            "subject": "Math",
                            "question_bangla": "বিন্দুর মধ্যবিন্দু কত?",
                            "question_english": "What is the midpoint?",
                            "question_both": "বিন্দুর মধ্যবিন্দু কত? (What is the midpoint?)",
                            "options": {
                                "both": {"ক": ",", "খ": ",", "গ": "(x₁+y₁, x₂+y₂)", "ঘ": ","},
                                "english": {"A": ",", "B": ",", "C": "(x1+y1, x2+y2)", "D": ","},
                            },
                            "answer": {"both": ["ক"], "english": ["A"]},
                            "semester": "Spring 2026",
                            "department": "CSE",
                        }
                    ],
                }
            ]
        )

        self.assertEqual(summary["created_count"], 0)
        self.assertEqual(summary["invalid_count"], 1)
        self.assertEqual(ScrappedQuestion.objects.count(), 0)

    def test_ingest_scraped_question_entries_preserves_bangla_and_duplicate_detection(self):
        valid_payload = {
            "filename": "good-math.docx",
            "data": [
                {
                    "subject": "Math",
                    "question_bangla": "২ + ২ কত?",
                    "question_english": "",
                    "question_both": "২ + ২ কত?",
                    "options": {
                        "both": {"ক": "3", "খ": "4", "গ": "5", "ঘ": "6"},
                        "english": {"A": "3", "B": "4", "C": "5", "D": "6"},
                    },
                    "answer": {"both": ["খ"], "english": ["B"]},
                    "semester": "Spring 2026",
                    "department": "CSE",
                }
            ],
        }

        first_summary = ingest_scraped_question_entries([valid_payload])
        second_summary = ingest_scraped_question_entries([valid_payload])

        self.assertEqual(first_summary["created_count"], 1)
        self.assertEqual(second_summary["skipped_duplicates"], 1)

        stored = ScrappedQuestion.objects.get()
        self.assertEqual(stored.questions["bangla"], "২ + ২ কত?")
        self.assertEqual(stored.questions["both"], "২ + ২ কত?")


class ScrappedQuestionUpdateTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]
        role = Role.objects.create(role_name=f"Admin-{suffix}")
        admin = User.objects.create(
            username=f"admin-{suffix}",
            email=f"admin-{suffix}@test.com",
            password=make_password("admin123"),
            role=role,
        )
        tokens = get_tokens_for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        self.question = ScrappedQuestion.objects.create(
            subject="Math",
            questions={"bangla": "২ + ২ কত?", "english": "", "both": "২ + ২ কত?"},
            type="option",
            options={
                "both": {"ক": "3", "খ": "4", "গ": "5", "ঘ": "6"},
                "english": {"A": "3", "B": "4", "C": "5", "D": "6"},
            },
            answer={"both": ["খ"], "english": ["B"]},
            marks=2,
            semester="Spring 2026",
            department_shortname="CSE",
        )

    def test_update_question_saves_both_languages_and_keeps_marks(self):
        response = self.client.patch(
            f"/api/question-bank/{self.question.id}/update/",
            {
                "subject": "Math",
                "question_bangla": "২ + ৩ কত?",
                "question_english": "What is 2 + 3?",
                "question_both": "২ + ৩ কত? (What is 2 + 3?)",
                "options": {
                    "both": {"ক": "4", "খ": "5", "গ": "6", "ঘ": "7"},
                    "english": {"A": "4", "B": "5", "C": "6", "D": "7"},
                },
                "answer": {"both": ["খ"], "english": ["B"]},
                "semester": "Spring 2026",
                "department": "CSE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.question.refresh_from_db()
        self.assertEqual(self.question.questions["bangla"], "২ + ৩ কত?")
        self.assertEqual(self.question.questions["english"], "What is 2 + 3?")
        self.assertEqual(self.question.options["english"]["B"], "5")
        self.assertEqual(self.question.marks, 2)  # preserved when not sent

    def test_update_question_rejects_invalid_payload(self):
        response = self.client.patch(
            f"/api/question-bank/{self.question.id}/update/",
            {
                "subject": "Math",
                "question_bangla": "২ + ৩ কত?",
                "question_english": "",
                "options": {
                    "both": {"ক": "4", "খ": "5"},
                    "english": {},
                },
                "answer": {"both": ["ঘ"], "english": []},
                "semester": "Spring 2026",
                "department": "CSE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.data["issues"])
        self.question.refresh_from_db()
        self.assertEqual(self.question.questions["bangla"], "২ + ২ কত?")  # unchanged
