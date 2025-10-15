from django.db import models
from .departments import Department


class MarksDistribution(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    ssc = models.IntegerField(default=0)
    hsc = models.IntegerField(default=0)
    diploma = models.IntegerField(default=0)
    main_marks = models.IntegerField(default=0)

    class Meta:
        db_table = "marks_distribution"

    def __str__(self):
        return f"Department: {self.department.department_name} | SSC: {self.ssc} | HSC: {self.hsc} | Diploma: {self.diploma}"
