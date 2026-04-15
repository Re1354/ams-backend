from django.db import models
from .scrapped_question import ScrappedQuestion
from .user import User
from ..utils import normalize_semester_value


class BlocklistQuestion(models.Model):
    # All fields from ScrappedQuestion as snapshot
    subject = models.CharField(max_length=255)
    questions = models.TextField()
    type = models.CharField(max_length=10, choices=ScrappedQuestion.TYPE_CHOICES)
    text = models.TextField(null=True, blank=True, default=None)
    options = models.JSONField(null=True, blank=True, default=None)
    answer = models.JSONField(null=True, blank=True, default=None)
    marks = models.IntegerField(default=1)
    semester = models.TextField()
    department_shortname = models.TextField(default='CSE')
    
    # Additional blocklist specific fields
    original_question_id = models.IntegerField(help_text="ID of the original scrapped question")
    remarks = models.TextField(help_text="Reason for blocking this question")
    creator = models.ForeignKey(User, on_delete=models.CASCADE, related_name="blocked_questions")
    issue_solved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def create_from_scrapped_question(cls, scrapped_question, creator, remarks):
        """Create a BlocklistQuestion from a ScrappedQuestion instance"""
        return cls.objects.create(
            subject=scrapped_question.subject,
            questions=scrapped_question.questions,
            type=scrapped_question.type,
            text=scrapped_question.text,
            options=scrapped_question.options,
            answer=scrapped_question.answer,
            marks=scrapped_question.marks,
            semester=scrapped_question.semester,
            department_shortname=scrapped_question.department_shortname,
            original_question_id=scrapped_question.id,
            remarks=remarks,
            creator=creator
        )

    def restore_to_scrapped_question(self):
        """Restore this blocked question back to ScrappedQuestion"""
        return ScrappedQuestion.objects.create(
            subject=self.subject,
            questions=self.questions,
            type=self.type,
            text=self.text,
            options=self.options,
            answer=self.answer,
            marks=self.marks,
            semester=self.semester,
            department_shortname=self.department_shortname
        )

    class Meta:
        db_table = "blocklist_questions"

    def save(self, *args, **kwargs):
        self.semester = normalize_semester_value(self.semester)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Blocked: {self.subject} - {self.questions[:50]}..."
