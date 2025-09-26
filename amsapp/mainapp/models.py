from django.db import models
import json
from django.contrib.postgres.fields import ArrayField
# Create your models here.

class ScrappedQuestion(models.Model):
    TYPE_CHOICES = [
        ('option', 'Option'),
        ('text', 'Text'),
    ]
    
    subject = models.CharField(max_length=255)
    questions = models.TextField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    text = models.TextField(null=True, blank=True, default=None)
    options = models.JSONField(null=True, blank=True, default=None)
    answer = models.JSONField(null=True, blank=True, default=None)
    marks = models.IntegerField(default=1)
    semester = models.TextField()
    
    class Meta:
        db_table = 'scrapped_questions'
    
    def __str__(self):
        return f"{self.subject} - {self.questions[:50]}..."


class Exam(models.Model):
    department = models.CharField(max_length=255)
    semester = models.CharField(max_length=50)
    total_questions = models.IntegerField(help_text="Maximum allowed questions for this exam")
    present_question = models.IntegerField(default=0, help_text="Current number of questions in this exam")
    total_marks = models.IntegerField()
    duration_minutes = models.IntegerField()
    except_semesters = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list,
        help_text="List of semesters to exclude"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Exam {self.id} - {self.department}"


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

    def __str__(self):
        return f"Exam {self.exam.id} -> {self.subject}"