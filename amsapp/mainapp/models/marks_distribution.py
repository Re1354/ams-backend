from django.db import models
from .departments import Department
from .faculty import Faculty


class MarksDistribution(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='marks_distributions',
        help_text="The faculty associated with marks distribution. All departments under this faculty share this distribution."
    )
    ssc = models.IntegerField(default=0)
    hsc = models.IntegerField(default=0)
    diploma = models.IntegerField(default=0)
    main_marks = models.IntegerField(default=0)
    viva_marks = models.IntegerField(default=0)

    class Meta:
        db_table = "marks_distribution"

    def __str__(self):
        target = self.faculty.faculty_name if self.faculty else (self.department.department_name if self.department else 'Unassigned')
        return f"Target: {target} | SSC: {self.ssc} | HSC: {self.hsc} | Diploma: {self.diploma} | Viva: {self.viva_marks}"
