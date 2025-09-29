from django.db import models
from .students import Students
from .exam import Exam
from .exam_question import ExamQuestion


class Submission(models.Model):
    student = models.ForeignKey(Students, on_delete=models.CASCADE, related_name="submissions")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="submissions")
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name="submissions")
    answer = models.TextField()
    is_correct = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'submission'
        unique_together = ['student', 'exam', 'question']  # Prevent duplicate submissions

    def __str__(self):
        return f"{self.student.username} - Exam {self.exam.id} - Q{self.question.id}"
