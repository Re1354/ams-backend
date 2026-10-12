from django.db import models
from .departments import Department
from .faculty import Faculty


class VivaRubrics(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='viva_rubrics',
        help_text="The faculty associated with the rubrics. All departments in this faculty share these rubrics."
    )
    rubrics = models.TextField()
    marks = models.IntegerField(default=1)

    class Meta:
        db_table = "viva_rubrics"

    def __str__(self):
        target = self.faculty.faculty_name if self.faculty else (self.department.department_name if self.department else 'Unassigned')
        return f"Target: {target} | Marks: {self.marks}"