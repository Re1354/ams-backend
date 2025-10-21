from django.db import models


class Students(models.Model):
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)  # In real app, use hashed passwords
    f_id = models.CharField(max_length=50, help_text="Form ID")
    full_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    department_shortname = models.CharField(max_length=50, default='CSE', help_text="Department short name")
    created_at = models.DateTimeField(auto_now_add=True)
    ssc = models.IntegerField(default=0)
    hsc = models.IntegerField(default=0)
    diploma = models.IntegerField(default=0)

    class Meta:
        db_table = 'students'

    def __str__(self):
        return f"{self.username} ({self.f_id})"
