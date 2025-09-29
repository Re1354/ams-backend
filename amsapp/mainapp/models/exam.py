from django.db import models
from django.contrib.postgres.fields import ArrayField


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
