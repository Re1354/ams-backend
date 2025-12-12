from django.db import models
from django.core.validators import MinValueValidator
from .exam import Exam
from .students import Students
from .departments import Department


class AdmissionResult(models.Model):
    """
    Stores the final calculated admission status of a student for a specific exam.
    Includes breakdown of marks and selection status based on department threshold.
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PUBLISHED', 'Published'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    exam = models.ForeignKey(
        Exam, 
        on_delete=models.CASCADE, 
        related_name="admission_results",
        help_text="The exam this result belongs to"
    )
    student = models.ForeignKey(
        Students, 
        on_delete=models.CASCADE, 
        related_name="admission_results",
        help_text="The student this result belongs to"
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="admission_results",
        help_text="Department the student applied for",
        null=True,
        blank=True
    )
    mcq_marks = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Marks obtained in MCQ portion"
    )
    viva_marks = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Marks obtained in viva portion"
    )
    total_marks = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Total marks (MCQ + Viva)"
    )
    subject_wise_marks = models.JSONField(
        default=dict,
        help_text="Subject-wise breakdown of marks in JSON format"
    )
    is_selected = models.BooleanField(
        default=False,
        help_text="True if total marks >= department threshold"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING',
        help_text="Publication status of the result"
    )
    threshold_applied = models.FloatField(
        null=True,
        blank=True,
        help_text="The threshold that was applied during calculation"
    )
    remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Additional remarks or notes about the result"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admission_result'
        unique_together = ['exam', 'student']  # One result per student per exam
        indexes = [
            models.Index(fields=['exam', 'student']),
            models.Index(fields=['exam', 'is_selected']),
            models.Index(fields=['exam', 'department']),
            models.Index(fields=['status']),
            models.Index(fields=['is_selected']),
        ]
        ordering = ['-total_marks', '-created_at']

    def __str__(self):
        selected_status = "Selected" if self.is_selected else "Not Selected"
        return f"{self.student.username} - Exam {self.exam.id}: {self.total_marks} ({selected_status})"

    def save(self, *args, **kwargs):
        """Override save to ensure total_marks is calculated"""
        self.total_marks = self.mcq_marks + self.viva_marks
        super().save(*args, **kwargs)
