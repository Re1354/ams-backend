from django.db import models
from .role import Role
from .departments import Department
from .faculty import Faculty


class User(models.Model):
    ACCESS_TYPE_CHOICES = (
        ('GLOBAL', 'Global'),
        ('FACULTY', 'Faculty'),
        ('DEPARTMENT', 'Department'),
    )

    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=255)  # should be hashed in real apps
    image = models.FileField(upload_to='user_profiles/', null=True, blank=True)
    employee_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    designation = models.CharField(max_length=255, blank=True)
    personal_email = models.EmailField(null=True, blank=True)
    university_email = models.EmailField(unique=True, null=True, blank=True)
    contact = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="users", null=True, blank=True)
    
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPE_CHOICES, default='DEPARTMENT')
    is_global_access = models.BooleanField(default=False)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='users', null=True, blank=True)
    
    class Meta:
        db_table = 'users'

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def __str__(self):
        return f"{self.username} ({self.role.role_name if self.role else 'No Role'})"
