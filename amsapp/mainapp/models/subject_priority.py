from django.db import models
from .departments import Department
from .subjects import Subject


class SubjectPriority(models.Model):
    """
    Department-wise subject priority mapping for admission tie-breaking.
    Example:
        CSE: Priority 1 = IT, Priority 2 = Math, Priority 3 = Physics, Priority 4 = English, Priority 5 = GK
    """

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="subject_priorities",
        help_text="The department this priority belongs to.",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="priority_mappings",
        help_text="The subject being prioritized.",
    )
    priority = models.PositiveIntegerField(
        help_text="Priority rank (1 is highest priority, 2 is next, etc.)."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subject_priorities"
        ordering = ["department", "priority"]
        unique_together = [
            ("department", "subject"),
            ("department", "priority"),
        ]

    def __str__(self):
        dept_name = self.department.department_shortname or self.department.department_name
        return f"{dept_name} - Priority {self.priority}: {self.subject.subject_name}"


# Alias for convenience and semantic consistency
SubjectPriorityMapping = SubjectPriority
