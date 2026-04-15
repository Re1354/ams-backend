from django.db import models
from ..utils import normalize_semester_value


class Students(models.Model):
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
    hsc = models.FloatField(default=0)
    diploma = models.FloatField(default=0)

    class Meta:
        db_table = 'students'

    def save(self, *args, **kwargs):
        self.registration_semester = normalize_semester_value(self.registration_semester)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.f_id})"
