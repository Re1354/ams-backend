from django.db import models
from .exam import Exam
from .scrapped_question import ScrappedQuestion
from ..utils import normalize_semester_value


class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="exam_questions")

    # Snapshot of ScrappedQuestion fields
    subject = models.CharField(max_length=255)
    question_text = models.TextField()
    type = models.CharField(max_length=10, choices=ScrappedQuestion.TYPE_CHOICES)
    text = models.TextField(null=True, blank=True)
    options = models.JSONField(null=True, blank=True)
    answer = models.TextField(null=True, blank=True)
    marks = models.IntegerField(default=1)
    semester = models.TextField(null=True, blank=True, default='')
    department_shortname = models.TextField(default='CSE')

    def save(self, *args, **kwargs):
        self.semester = normalize_semester_value(self.semester, allow_blank=True)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Exam {self.exam.id} -> {self.subject}"
