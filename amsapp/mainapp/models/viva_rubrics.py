from django.db import models
from .departments import Department


class VivaRubrics(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    rubrics = models.TextField()
    marks = models.IntegerField(default=1)

    class Meta:
        db_table = "viva_rubrics"

    def __str__(self):
        return f"Department: {self.department.department_name} | Marks: {self.marks}"