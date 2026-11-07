from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class AdmissionReportSignatory(models.Model):
    ROLE_CONVENOR = "CONVENOR"
    ROLE_DEPARTMENT_HEAD = "DEPARTMENT_HEAD"
    ROLE_DEAN = "DEAN"
    ROLE_CHOICES = [
        (ROLE_CONVENOR, "Convenor, Admission Test Committee"),
        (ROLE_DEPARTMENT_HEAD, "Department Head"),
        (ROLE_DEAN, "Faculty Dean"),
    ]

    role = models.CharField(max_length=32, choices=ROLE_CHOICES)
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255)
    department = models.ForeignKey(
        "mainapp.Department",
        on_delete=models.CASCADE,
        related_name="admission_report_signatories",
        null=True,
        blank=True,
    )
    faculty = models.ForeignKey(
        "mainapp.Faculty",
        on_delete=models.CASCADE,
        related_name="admission_report_signatories",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admission_report_signatories"
        ordering = ["role", "department_id", "faculty_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["role", "department"],
                condition=Q(role__in=["CONVENOR", "DEPARTMENT_HEAD"]),
                name="uniq_admission_report_dept_signatory",
            ),
            models.UniqueConstraint(
                fields=["role", "faculty"],
                condition=Q(role="DEAN"),
                name="uniq_admission_report_faculty_dean",
            ),
        ]

    def clean(self):
        super().clean()
        self.name = (self.name or "").strip()
        self.designation = (self.designation or "").strip()
        if self.role == self.ROLE_DEAN:
            if not self.faculty_id or self.department_id:
                raise ValidationError(
                    "A faculty dean requires a faculty and cannot be linked to a department."
                )
        elif self.role in {self.ROLE_CONVENOR, self.ROLE_DEPARTMENT_HEAD}:
            if not self.department_id or self.faculty_id:
                raise ValidationError(
                    "Convenor and department-head records require a department and cannot be linked to a faculty."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        scope = self.department or self.faculty
        return f"{self.get_role_display()} - {scope}"
