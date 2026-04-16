import json

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Exam, ExamQuestion, PublishedExam, Students, Submission
from ..utils import calculate_submission_summary, is_submission_correct


class ExamScoringUtilityTests(TestCase):
    def setUp(self):
        self.exam = Exam.objects.create(
            department="CSE",
            semester="Spring 2026",
            total_questions=2,
            present_question=2,
            total_marks=10,
            duration_minutes=60,
        )
        self.question = ExamQuestion.objects.create(
            exam=self.exam,
            subject="English",
            question_text="Select the right answer",
            type="option",
            options={"A": "One", "B": "Two", "C": "Three", "D": "Four"},
            answer=json.dumps(["A"]),
            marks=5,
            semester="Spring 2026",
            department_shortname="CSE",
        )

    def test_option_answer_json_string_marks_correct(self):
        self.assertTrue(is_submission_correct(self.question, "A"))

    def test_option_answer_text_value_also_resolves_to_key(self):
        self.assertTrue(is_submission_correct(self.question, "One"))


class StudentExamResultScoringTests(APITestCase):
    def setUp(self):
        self.student = Students.objects.create(
            username="student1",
            password="pass123",
            f_id="F001",
            full_name="Student One",
            email="student1@test.com",
            department_shortname="CSE",
            registration_semester="Spring 2026",
        )
        self.exam = Exam.objects.create(
            department="CSE",
            semester="Spring 2026",
            total_questions=2,
            present_question=2,
            total_marks=10,
            duration_minutes=60,
        )
        self.question_1 = ExamQuestion.objects.create(
            exam=self.exam,
            subject="English",
            question_text="Question 1",
            type="option",
            options={"A": "One", "B": "Two", "C": "Three", "D": "Four"},
            answer=json.dumps(["A"]),
            marks=5,
            semester="Spring 2026",
            department_shortname="CSE",
        )
        self.question_2 = ExamQuestion.objects.create(
            exam=self.exam,
            subject="English",
            question_text="Question 2",
            type="option",
            options={"A": "Yes", "B": "No", "C": "Maybe", "D": "Later"},
            answer=json.dumps(["B"]),
            marks=5,
            semester="Spring 2026",
            department_shortname="CSE",
        )
        PublishedExam.objects.create(exam=self.exam, is_published=True)

    def test_submit_exam_marks_json_string_answer_correct(self):
        response = self.client.post(
            f"/api/student/exam/{self.exam.id}/submit/",
            {
                "student_id": self.student.id,
                "submissions": [{"question_id": self.question_1.id, "answer": "A"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        submission = Submission.objects.get(
            student=self.student, exam=self.exam, question=self.question_1
        )
        self.assertTrue(submission.is_correct)

    def test_student_result_uses_total_exam_marks_not_attempted_count(self):
        Submission.objects.create(
            student=self.student,
            exam=self.exam,
            question=self.question_1,
            answer="A",
            is_correct=True,
        )

        response = self.client.get(
            f"/api/student/exam/{self.exam.id}/result/{self.student.id}/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"]["correct_answers"], 1)
        self.assertEqual(response.data["results"]["score_percentage"], 50.0)

    def test_submission_summary_uses_marks_based_percentage(self):
        Submission.objects.create(
            student=self.student,
            exam=self.exam,
            question=self.question_1,
            answer="A",
            is_correct=True,
        )
        summary = calculate_submission_summary(
            self.exam,
            Submission.objects.filter(student=self.student, exam=self.exam).select_related(
                "question"
            ),
        )

        self.assertEqual(summary["obtained_marks"], 5)
        self.assertEqual(summary["total_marks"], 10)
        self.assertEqual(summary["score_percentage"], 50.0)
