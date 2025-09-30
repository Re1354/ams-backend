from django.db import models
from django.contrib.postgres.fields import ArrayField
from .departments import Department


class SubjectDepartment(models.Model):
    """
    A model to map a single department to multiple subjects.
    
    This uses an ArrayField to store a list of subject IDs for each department.
    """
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='subject_mappings',
        help_text="The department associated with the subjects."
    )
    
    subject_ids = ArrayField(
        models.IntegerField(),
        blank=True,
        default=list,
        help_text="An array of subject IDs belonging to the department."
    )
    class Meta:
        db_table = "subjects_departments"

    def __str__(self):
        return f"{self.department.department_name} - Subjects"