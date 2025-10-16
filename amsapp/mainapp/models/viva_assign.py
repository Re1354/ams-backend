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
    time = models.TimeField(default="00:30:00", help_text="Time allocated for viva")
    room = models.CharField(max_length=100, default="Room 101", help_text="Room for viva")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "viva_assignment"
        unique_together = ('student', 'teacher', 'exam')

    def __str__(self):
        return f"Student: {self.student.username} | Teacher: {self.teacher.username} | Exam ID: {self.exam.id} | Time: {self.time} | Room: {self.room}"
