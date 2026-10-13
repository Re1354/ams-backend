from django.db import models
from django.contrib.postgres.fields import ArrayField
from ..utils import normalize_semester_list, normalize_semester_value


class Exam(models.Model):
    EXAM_TYPE_CHOICES = [
        ('SCHEDULED', 'Scheduled'),
        ('CENTRAL', 'Central'),
    ]

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

    exam_type = models.CharField(
        max_length=20,
        choices=EXAM_TYPE_CHOICES,
        default='SCHEDULED',
        db_index=True,
        help_text="Scheduled (department-specific) or Central (faculty-wide)"
    )
    faculty_ref = models.ForeignKey(
        'mainapp.Faculty',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exams',
        help_text="Associated Faculty for Central or Scheduled exams"
    )

    class Meta:
        indexes = [
            models.Index(fields=['department', 'semester'], name='exam_dept_sem_idx'),
            models.Index(fields=['created_at'], name='exam_created_idx'),
            models.Index(fields=['exam_type'], name='exam_type_idx'),
        ]

    def save(self, *args, **kwargs):
        self.semester = normalize_semester_value(self.semester)
        self.except_semesters = normalize_semester_list(self.except_semesters)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Exam {self.id} [{self.exam_type}] - {self.department}"
