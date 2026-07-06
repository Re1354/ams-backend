from django.db import models
from .students import Students

class VivaMarks(models.Model):
    student = models.OneToOneField(Students, on_delete=models.CASCADE, related_name="viva_marks")
    marks = models.FloatField(default=0.0)
    rubrics_marks = models.JSONField(default=dict, help_text="Marks for each rubric in JSON format")
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'viva_marks'

    def __str__(self):
        return f"{self.student.username} - Viva Marks"
