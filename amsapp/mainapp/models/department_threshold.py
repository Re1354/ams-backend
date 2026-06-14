from django.db import models
from django.core.validators import MinValueValidator
from .exam import Exam
from .departments import Department


class DepartmentThreshold(models.Model):
    """
    Stores minimum marks threshold and seat limit for admission to a specific department in a specific semester.
    All exams within a semester share the same threshold and seat limit.
    Semester-based approach simplifies admin burden and provides semester-wide admission criteria.
    """
    exam = models.ForeignKey(
        Exam, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="department_thresholds",
        help_text="Optional: linked exam for reference (kept for backward compatibility)"
    )
    department = models.ForeignKey(
        Department, 
        on_delete=models.CASCADE, 
        related_name="admission_thresholds",
        help_text="The department this threshold applies to"
    )
    semester = models.CharField(
        max_length=20,
        default='Fall 2025',
        help_text="Semester in format 'Spring 2025', 'Summer 2025', 'Fall 2025', etc."
    )
    min_threshold_mark = models.FloatField(
        validators=[MinValueValidator(0.0)],
        help_text="Minimum marks required for admission to this department in this semester"
    )
    seat_limit = models.IntegerField(
        validators=[MinValueValidator(1)],
        default=10,
        help_text="Maximum number of students to accept for this department in this semester"
    )
    waiting_student_limit = models.IntegerField(
        validators=[MinValueValidator(0)],
        default=0,
        help_text="Maximum number of attended non-selected students to keep in waiting status"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'department_threshold'
        unique_together = ['semester', 'department']  # One threshold per dept per semester
        indexes = [
            models.Index(fields=['semester', 'department']),
            models.Index(fields=['semester']),
            models.Index(fields=['department']),
        ]

    def __str__(self):
        return (
            f"{self.semester} - {self.department.department_name}: "
            f"{self.min_threshold_mark} (seats: {self.seat_limit}, "
            f"waiting: {self.waiting_student_limit})"
        )

    def clean(self):
        """Validate that threshold is reasonable"""
        from django.core.exceptions import ValidationError
        if self.min_threshold_mark < 0:
            raise ValidationError("Threshold mark must be a positive number")
        if self.seat_limit < 1:
            raise ValidationError("Seat limit must be at least 1")
        if self.waiting_student_limit < 0:
            raise ValidationError("Waiting student limit cannot be negative")
