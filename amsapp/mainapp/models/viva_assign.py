from django.db import models
from .students import Students
from .user import User
from .exam import Exam


class VivaAssignment(models.Model):
    student = models.ForeignKey(
        Students,
        on_delete=models.CASCADE,
        related_name="assigned_viva_exams"
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assigned_student_viva_exams",
        help_text="Teacher who assigned the exam"
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="viva_assignments",  # ✅ unique related_name
        help_text="Related exam for the viva"
    )
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Scheduled date and time for the viva",
    )
    time = models.TimeField(default="00:30:00", help_text="Time allocated for viva")
    room = models.CharField(max_length=100, default="Room 101", help_text="Room for viva")
    total_marks = models.FloatField(default=0.0, help_text="Total viva marks for this exam")
    rubric_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text="Snapshot of the viva rubrics used for this student's exam",
    )
    rubric_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text="Awarded rubric scores keyed by rubric snapshot/source identifiers",
    )
    remarks = models.TextField(blank=True, null=True, help_text="Viva remarks for this exam")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "viva_assignment"
        unique_together = ('student', 'teacher', 'exam')
        indexes = [
            models.Index(fields=['teacher', 'exam'], name='viva_teacher_exam_idx'),
            models.Index(fields=['exam', 'created_at'], name='viva_exam_created_idx'),
            models.Index(fields=['teacher', 'created_at'], name='viva_teacher_created_idx'),
            models.Index(fields=['created_at'], name='viva_created_idx'),
            models.Index(fields=['scheduled_at'], name='viva_scheduled_idx'),
        ]

    def __str__(self):
        return (
            f"Student: {self.student.username} | Teacher: {self.teacher.username} | "
            f"Exam ID: {self.exam.id} | Time: {self.time} | Room: {self.room}"
        )
