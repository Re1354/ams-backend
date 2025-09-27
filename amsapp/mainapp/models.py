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


class ExamSchedule(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="schedules")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'exam_schedule'

    def __str__(self):
        return f"Schedule for Exam {self.exam.id} - {self.start_time}"


class Students(models.Model):
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)  # In real app, use hashed passwords
    f_id = models.CharField(max_length=50, help_text="Form ID")
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'students'

    def __str__(self):
        return f"{self.username} ({self.f_id})"


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