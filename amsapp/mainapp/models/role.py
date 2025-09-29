from django.db import models


class Role(models.Model):
    role_name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = 'roles'

    def __str__(self):
        return self.role_name
