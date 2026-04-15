from django.db import models
from ..utils import normalize_semester_value


class ScrappedQuestion(models.Model):
    TYPE_CHOICES = [
        ('option', 'Option'),
        ('text', 'Text'),
    ]

    subject = models.CharField(max_length=255)
    questions = models.JSONField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES,default='option')
    text = models.TextField(null=True, blank=True, default=None)
    options = models.JSONField(null=True, blank=True, default=None)
    answer = models.JSONField(null=True, blank=True, default=None)
    marks = models.IntegerField(default=1)
    semester = models.TextField()
    department_shortname = models.TextField(default='CSE')

    class Meta:
        db_table = 'scrapped_questions'

    def save(self, *args, **kwargs):
        self.semester = normalize_semester_value(self.semester)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.subject} - {self.questions[:50]}..."
