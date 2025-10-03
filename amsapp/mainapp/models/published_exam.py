from django.db import models
from .exam import Exam


class PublishedExam(models.Model):
    exam = models.OneToOneField(Exam, on_delete=models.CASCADE, related_name="published_status")
    is_published = models.BooleanField(default=False, help_text="Whether the exam results are published")
    published_at = models.DateTimeField(null=True, blank=True, help_text="When the results were published")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'published_exam'
        indexes = [
            models.Index(fields=['exam', 'is_published']),
            models.Index(fields=['is_published']),
        ]

    def __str__(self):
        status = "Published" if self.is_published else "Not Published"
        return f"Exam {self.exam.id} - {status}"

    def save(self, *args, **kwargs):
        if self.is_published and not self.published_at:
            from django.utils import timezone
            self.published_at = timezone.now()
        elif not self.is_published:
            self.published_at = None
        super().save(*args, **kwargs)