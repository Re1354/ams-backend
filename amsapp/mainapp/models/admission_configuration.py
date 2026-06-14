from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .departments import Department
from .exam import Exam
from ..utils import normalize_semester_value


class AdmissionConfiguration(models.Model):
    """
    Stores reusable admission constraints for a department and semester.

    This lets the system reuse the same seat limit and threshold across result
    calculations without asking the operator to enter them on every run.
    """

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="admission_configurations",
    )
    semester = models.CharField(max_length=50, db_index=True)
    exam = models.ForeignKey(
        Exam,
        on_delete=models.SET_NULL,
        related_name="admission_configurations",
        null=True,
        blank=True,
        help_text="Most recent exam linked to this admission semester",
    )
    seat_limit = models.PositiveIntegerField(
        default=0,
        help_text="Maximum number of students that can be accepted for this semester",
    )
    waiting_student_limit = models.PositiveIntegerField(
        default=0,
        help_text="Maximum number of attended non-selected students to keep in waiting status",
    )
    threshold = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Minimum weighted total required to stay in the waiting list",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admission_configuration"
        unique_together = ["department", "semester"]
        indexes = [
            models.Index(fields=["department", "semester"]),
            models.Index(fields=["semester"]),
        ]
        ordering = ["department__department_name", "semester"]

    def __str__(self):
        return f"{self.department.department_shortname} - {self.semester}"

    def save(self, *args, **kwargs):
        self.semester = normalize_semester_value(self.semester)
        super().save(*args, **kwargs)
