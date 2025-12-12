from django.db import models
from django.core.validators import MinValueValidator
from .exam import Exam
from .departments import Department


class DepartmentThreshold(models.Model):
    """
    Stores minimum marks threshold for admission to a specific department in a specific exam.
    Ensures historical data integrity by linking to specific exam instances.
    """
    exam = models.ForeignKey(
        Exam, 
        on_delete=models.CASCADE, 
        related_name="department_thresholds",
        help_text="The exam for which this threshold applies"
    )
    department = models.ForeignKey(
        Department, 
        on_delete=models.CASCADE, 
        related_name="admission_thresholds",
        help_text="The department this threshold applies to"
    )
    min_threshold_mark = models.FloatField(
        validators=[MinValueValidator(0.0)],
        help_text="Minimum marks required for admission to this department"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'department_threshold'
        unique_together = ['exam', 'department']  # One threshold per dept per exam
        indexes = [
            models.Index(fields=['exam', 'department']),
            models.Index(fields=['exam']),
        ]

    def __str__(self):
        return f"{self.exam.id} - {self.department.department_name}: {self.min_threshold_mark}"

    def clean(self):
        """Validate that threshold is reasonable"""
        from django.core.exceptions import ValidationError
        if self.min_threshold_mark < 0:
            raise ValidationError("Threshold mark must be a positive number")
        if hasattr(self, 'exam') and self.exam and self.min_threshold_mark > self.exam.total_marks:
            raise ValidationError(
                f"Threshold ({self.min_threshold_mark}) cannot exceed exam total marks ({self.exam.total_marks})"
            )
