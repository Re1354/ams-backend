from django.db import models
from .students import Students
from .exam import Exam
from .exam_question import ExamQuestion


class ExamDraft(models.Model):
    """A student's in-progress answer, autosaved while taking an exam.

    Drafts are intentionally kept separate from `Submission`. A draft only
    preserves work so a student can rejoin after a reload or a device that
    switched off mid-exam; it is NOT a submission. Only clicking "Submit" or
    the exam timer reaching zero creates real `Submission` rows.
    """

    student = models.ForeignKey(Students, on_delete=models.CASCADE, related_name="exam_drafts")
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="exam_drafts")
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name="exam_drafts")
    answer = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'exam_draft'
        unique_together = ['student', 'exam', 'question']

    def __str__(self):
        return f"Draft {self.student.username} - Exam {self.exam.id} - Q{self.question.id}"
