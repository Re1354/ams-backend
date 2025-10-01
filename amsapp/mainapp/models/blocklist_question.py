from django.db import models
from .scrapped_question import ScrappedQuestion
from .user import User


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

    class Meta:
        db_table = "blocklist_questions"

    def __str__(self):
        return f"Blocked: {self.subject} - {self.questions[:50]}..."