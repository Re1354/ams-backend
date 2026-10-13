from django.db import models


class Faculty(models.Model):
    faculty_name = models.CharField(max_length=255, unique=True)
    faculty_shortname = models.CharField(max_length=50)

    class Meta:
        db_table = "faculties"

    @property
    def faculty_code(self):
        return self.faculty_shortname

    def __str__(self):
        return self.faculty_name
