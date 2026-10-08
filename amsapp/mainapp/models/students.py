from django.db import models
# pyrefly: ignore [missing-import]
from ..utils import normalize_semester_value


class Students(models.Model):
    ACADEMIC_TYPE_CHOICES = [
        ('HSC', 'HSC'),
        ('DIPLOMA', 'Diploma'),
    ]

    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)  # In real app, use hashed passwords
    f_id = models.CharField(max_length=50, help_text="Form ID")
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    department_shortname = models.CharField(max_length=50, default='CSE', help_text="Department short name")
    registration_semester = models.CharField(
        max_length=50,
        help_text="Semester or intake when the student registered",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ssc = models.FloatField(default=0)
    academic_type = models.CharField(
        max_length=20,
        choices=ACADEMIC_TYPE_CHOICES,
        default='HSC',
        help_text="Whether the student uses HSC GPA or Diploma CGPA",
    )
    hsc = models.FloatField(default=0)
    diploma = models.FloatField(default=0)

    # Faculty / department choices (admission preference flow)
    faculty = models.ForeignKey(
        'mainapp.Faculty',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='applicants',
        help_text="Faculty the student is applying under",
    )
    department_choices = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Ordered list of up to 3 department preferences. "
            'Each entry: {"department_id": <int>, "priority": <int>}'
        ),
    )

    class Meta:
        db_table = 'students'
        indexes = [
            models.Index(fields=['department_shortname', 'registration_semester'], name='students_dept_sem_idx'),
            models.Index(fields=['f_id'], name='students_fid_idx'),
            models.Index(fields=['created_at'], name='students_created_idx'),
        ]

    def save(self, *args, **kwargs):
        self.registration_semester = normalize_semester_value(self.registration_semester)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.f_id})"
