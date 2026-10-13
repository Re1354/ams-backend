from django.db import models
from django.contrib.postgres.fields import ArrayField
from .faculty import Faculty


class SubjectFaculty(models.Model):
    """
    A model to map a single faculty to multiple subjects.
    
    This uses an ArrayField to store a list of subject IDs for each faculty.
    All departments under the faculty inherit these subjects.
    """
    faculty = models.OneToOneField(
        Faculty,
        on_delete=models.CASCADE,
        related_name='subject_mappings',
        help_text="The faculty associated with the subjects."
    )
    
    subject_ids = ArrayField(
        models.IntegerField(),
        blank=True,
        default=list,
        help_text="An array of subject IDs belonging to the faculty."
    )

    class Meta:
        db_table = "subjects_faculties"

    def __str__(self):
        return f"{self.faculty.faculty_name} - Subjects"
