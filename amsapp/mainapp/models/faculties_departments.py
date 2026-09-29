from django.db import models
from django.contrib.postgres.fields import ArrayField
from .faculty import Faculty


class FacultyDepartment(models.Model):
    """
    A model to map a single faculty to multiple departments.
    This uses an ArrayField to store a list of department IDs for each faculty.
    """
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='department_mappings',
        help_text="The faculty associated with the departments."
    )
    
    department_ids = ArrayField(
        models.IntegerField(),
        blank=True,
        default=list,
        help_text="An array of department IDs belonging to the faculty."
    )

    class Meta:
        db_table = "faculties_departments"

    def __str__(self):
        return f"{self.faculty.faculty_name} - Departments"
