from django.db import models


class Department(models.Model):
    department_name = models.CharField(max_length=255, unique=True)
    department_shortname = models.CharField(max_length=50)

    class Meta:
        db_table = "departments"

    def __str__(self):
        return self.department_name
