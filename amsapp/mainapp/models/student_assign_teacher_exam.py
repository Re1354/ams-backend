from django.db import models
from .students import Students
from .user import User
from .exam import Exam
from .exam_schedule import ExamSchedule


class StudentAssignTeacherExam(models.Model):
    student = models.ForeignKey(Students, on_delete=models.CASCADE, related_name="assigned_exams")
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name="assigned_student_exams", help_text="Teacher who assigned the exam")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="student_assignments")
    schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE, related_name="assigned_exams", help_text="Schedule of the exam",default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student_assign_teacher_exam"
        unique_together = ('student', 'teacher', 'schedule')  # Prevent duplicate assignments for same schedule
        indexes = [
            models.Index(fields=['student', 'exam']),
            models.Index(fields=['teacher', 'exam']),
            models.Index(fields=['student', 'schedule']),
            models.Index(fields=['created_at']),
        ]

    def save(self, *args, **kwargs):
        # Automatically set exam from schedule if not already set
        if self.schedule and not self.exam:
            self.exam = self.schedule.exam
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Student: {self.student.username} | Teacher: {self.teacher.username} | Exam: {self.exam.id}"