from django.db import models


class ScrappedQuestion(models.Model):
    TYPE_CHOICES = [
        ('option', 'Option'),
        ('text', 'Text'),
    ]

    subject = models.CharField(max_length=255)
    questions = models.TextField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    text = models.TextField(null=True, blank=True, default=None)
    options = models.JSONField(null=True, blank=True, default=None)
    answer = models.JSONField(null=True, blank=True, default=None)
    marks = models.IntegerField(default=1)
    semester = models.TextField()
    department_shortname = models.TextField(default='CSE')

    class Meta:
        db_table = 'scrapped_questions'

    def __str__(self):
        return f"{self.subject} - {self.questions[:50]}..."
