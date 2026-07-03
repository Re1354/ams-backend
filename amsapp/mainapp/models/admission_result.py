from django.db import models
from django.core.validators import MinValueValidator
from .admission_configuration import AdmissionConfiguration
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

    RESULT_STATUS_CHOICES = [
        ('SELECTED', 'Selected'),
        ('WAITING', 'Waiting'),
        ('REJECTED', 'Rejected'),
        ('ABSENT', 'Absent'),
    ]

    ACADEMIC_SOURCE_CHOICES = [
        ('HSC', 'HSC'),
        ('DIPLOMA', 'Diploma'),
        ('NONE', 'None'),
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
    configuration = models.ForeignKey(
        AdmissionConfiguration,
        on_delete=models.SET_NULL,
        related_name="results",
        null=True,
        blank=True,
        help_text="Semester-level admission configuration used for this result",
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
    written_viva_total = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Raw total of written and viva marks"
    )
    total_marks = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Total marks (MCQ + Viva)"
    )
    weighted_total_marks = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Final weighted total after applying marks distribution"
    )
    attended_exam = models.BooleanField(
        default=False,
        help_text="Whether the student participated in the exam"
    )
    result_status = models.CharField(
        max_length=20,
        choices=RESULT_STATUS_CHOICES,
        default='WAITING',
        help_text="Final admission board status for this candidate"
    )
    is_override_accepted = models.BooleanField(
        default=False,
        help_text="True if candidate is manually accepted and locked as selected"
    )
    is_admitted = models.BooleanField(
        default=False,
        help_text="True if admission is confirmed; survives recalculation and holds a seat"
    )
    ssc_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Raw SSC score stored with the calculated result"
    )
    academic_score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Raw HSC or Diploma score stored with the calculated result"
    )
    academic_source = models.CharField(
        max_length=20,
        choices=ACADEMIC_SOURCE_CHOICES,
        default='NONE',
        help_text="Which academic score was used in the weighted calculation"
    )
    ssc_contribution = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Weighted SSC contribution"
    )
    academic_contribution = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Weighted HSC/Diploma contribution"
    )
    written_contribution = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Weighted written contribution"
    )
    viva_contribution = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0)],
        help_text="Weighted viva contribution"
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
            models.Index(fields=['result_status']),
            models.Index(fields=['is_override_accepted'], name='admission_r_is_over_8b945e_idx'),
            models.Index(fields=['is_admitted'], name='admission_r_is_admt_idx'),
            models.Index(fields=['configuration']),
            models.Index(fields=['department', 'configuration'], name='admission_dept_config_idx'),
            models.Index(fields=['status', 'result_status'], name='admission_status_result_idx'),
            models.Index(fields=['weighted_total_marks'], name='admission_weighted_idx'),
            models.Index(fields=['created_at'], name='admission_created_idx'),
        ]
        ordering = ['-weighted_total_marks', '-total_marks', '-created_at']

    def __str__(self):
        return (
            f"{self.student.username} - Exam {self.exam.id}: "
            f"{self.weighted_total_marks} ({self.result_status})"
        )

    def save(self, *args, **kwargs):
        """Override save to ensure total_marks is calculated"""
        self.total_marks = self.mcq_marks + self.viva_marks
        self.written_viva_total = self.total_marks
        super().save(*args, **kwargs)
