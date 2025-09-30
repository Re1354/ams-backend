from django.db import models


class Subject(models.Model):
    subject_name = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = "subjects"

    def __str__(self):
        return self.subject_name
