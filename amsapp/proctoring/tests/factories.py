"""Small builders for proctoring tests (real AMS rows, no mocks)."""
import base64
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.utils import timezone

from mainapp.models import (
    Department,
    Exam,
    ExamSchedule,
    Role,
    RoleMenu,
    Menu,
    StudentAssignTeacherExam,
    Students,
    User,
)
from mainapp.tokens import get_tokens_for_user

# Smallest valid JPEG (1x1 px).
TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////"
    "////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBAB"
    "AAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)

PROCTORING_LINK = "/proctoring"


def suffix() -> str:
    return uuid4().hex[:8]


def make_user(role_name="superadmin", **extra) -> User:
    s = suffix()
    role, _ = Role.objects.get_or_create(role_name=role_name)
    return User.objects.create(
        username=f"user_{s}",
        email=f"user_{s}@example.com",
        password=make_password("Secret123!"),
        role=role,
        **extra,
    )


def auth_header(user: User) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {get_tokens_for_user(user)['access']}"}


def grant(role_name: str, **permissions) -> None:
    """Give a role access to the Proctoring menu with the given permissions."""
    role, _ = Role.objects.get_or_create(role_name=role_name)
    menu, _ = Menu.objects.get_or_create(
        link=PROCTORING_LINK,
        defaults={"label": "Proctoring", "component": "ProctoringDashboard", "icon": "Eye"},
    )
    perms = {"read": False, "write": False, "edit": False, "delete": False, **permissions}
    RoleMenu.objects.update_or_create(role=role, menu=menu, defaults={"permissions": perms})


def make_department(shortname="CSE") -> Department:
    return Department.objects.create(
        department_name=f"Department {shortname} {suffix()}", department_shortname=shortname
    )


def make_exam(department="CSE", semester="Fall 2026") -> Exam:
    return Exam.objects.create(
        department=department,
        semester=semester,
        total_marks=100,
        total_questions=50,
        duration_minutes=60,
    )


def make_schedule(exam: Exam, start_offset_min=-5, end_offset_min=60) -> ExamSchedule:
    now = timezone.now()
    return ExamSchedule.objects.create(
        exam=exam,
        start_time=now + timedelta(minutes=start_offset_min),
        end_time=now + timedelta(minutes=end_offset_min),
    )


def make_student(username=None, department_shortname="CSE", department_choices=None, **extra) -> Students:
    s = suffix()
    return Students.objects.create(
        username=username or f"applicant_{s}",
        password="x",
        f_id=f"F-{s}",
        full_name=extra.pop("full_name", f"Applicant {s}"),
        department_shortname=department_shortname,
        registration_semester="Fall 2026",
        department_choices=department_choices or [],
        **extra,
    )


def assign(student: Students, exam: Exam, schedule: ExamSchedule, teacher: User | None = None):
    return StudentAssignTeacherExam.objects.create(
        student=student, exam=exam, schedule=schedule, teacher=teacher or make_user("teacher")
    )


def exam_window(start_offset_min=-5, end_offset_min=60, department="CSE", semester="Fall 2026"):
    """An exam with an open window and one assigned student: (student, exam, schedule)."""
    exam = make_exam(department=department, semester=semester)
    schedule = make_schedule(exam, start_offset_min, end_offset_min)
    student = make_student(department_shortname=department)
    assign(student, exam, schedule)
    return student, exam, schedule
