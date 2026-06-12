from django.db import models
from .exam import Exam


class ExamSchedule(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="schedules")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'exam_schedule'
        indexes = [
            models.Index(fields=['start_time'], name='schedule_start_idx'),
            models.Index(fields=['exam', 'start_time'], name='schedule_exam_start_idx'),
            models.Index(fields=['is_active', 'start_time'], name='schedule_active_start_idx'),
        ]

    def __str__(self):
        return f"Schedule for Exam {self.exam.id} - {self.start_time}"
