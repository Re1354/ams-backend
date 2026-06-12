from django.db import models
from django.contrib.postgres.fields import ArrayField
from ..utils import normalize_semester_list, normalize_semester_value


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
    language = models.CharField(max_length=50, default='English')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    faculty = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['department', 'semester'], name='exam_dept_sem_idx'),
            models.Index(fields=['created_at'], name='exam_created_idx'),
        ]

    def save(self, *args, **kwargs):
        self.semester = normalize_semester_value(self.semester)
        self.except_semesters = normalize_semester_list(self.except_semesters)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Exam {self.id} - {self.department}"
