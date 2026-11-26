"""Demo data for trying proctoring end to end on a LOCAL database only.

Creates (or refreshes) one CSE exam whose window is open now, five demo
applicants, an exam admin login, the support unlock code, and calculated
results for four of them:
  demo2 reported (4 counted flags), demo3 clear (1 flag), demo4 not monitored,
  demo5 low score; demo1 is left to take the exam in the student portal.

Refuses to run unless the database is on this computer (127.0.0.1/localhost).
The logins below are local test values only.
"""
import json
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from mainapp.models import (
    Department,
    DepartmentThreshold,
    Exam,
    ExamQuestion,
    ExamSchedule,
    MarksDistribution,
    Role,
    StudentAssignTeacherExam,
    Students,
    Submission,
    User,
)
from proctoring import services
from proctoring.models import ProctorSession

SEMESTER = "Spring 2027"
ADMIN_USERNAME = "e2e_admin"
ADMIN_PASSWORD = "E2e-Admin-2026!"
TEACHER_USERNAME = "e2e_teacher"
STUDENT_PASSWORD = "demo-pass-1"
# Support unlock code for this local demo (what support staff type on a student's PC).
UNLOCK_CODE = "support-e2e-7319"
QUESTIONS = 10
# name -> (correct answers out of 10, counted flags or None for no session)
APPLICANTS = {
    "demo1": (None, None),
    "demo2": (9, 4),
    "demo3": (8, 1),
    "demo4": (7, None),
    "demo5": (3, 0),
}
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Command(BaseCommand):
    help = "Local-only demo data for the proctoring end-to-end check."

    def handle(self, *args, **options):
        host = (connection.settings_dict.get("HOST") or "").strip()
        if host not in LOCAL_HOSTS:
            raise CommandError("Refusing: this command only runs against a database on this computer.")

        from mainapp.services.admission_calculator import calculate_semester_admission_results

        with transaction.atomic():
            superadmin, _ = Role.objects.get_or_create(role_name="superadmin")
            teacher_role, _ = Role.objects.get_or_create(role_name="teacher")
            admin, _ = User.objects.update_or_create(
                username=ADMIN_USERNAME,
                defaults={"email": "e2e_admin@example.com", "password": make_password(ADMIN_PASSWORD), "role": superadmin},
            )
            teacher, _ = User.objects.update_or_create(
                username=TEACHER_USERNAME,
                defaults={"email": "e2e_teacher@example.com", "password": make_password(ADMIN_PASSWORD), "role": teacher_role},
            )
            services.set_unlock_code(UNLOCK_CODE, admin)

            cse, _ = Department.objects.get_or_create(
                department_name="Computer Science and Engineering (demo)", defaults={"department_shortname": "CSE"}
            )
            MarksDistribution.objects.update_or_create(
                department=cse, defaults={"ssc": 0, "hsc": 0, "diploma": 0, "main_marks": 100, "viva_marks": 0}
            )
            DepartmentThreshold.objects.update_or_create(
                department=cse,
                semester=SEMESTER,
                defaults={"min_threshold_mark": 40.0, "seat_limit": 2, "waiting_student_limit": 1},
            )

            exam = Exam.objects.filter(department="CSE", semester=SEMESTER).order_by("id").first()
            if exam is None:
                exam = Exam.objects.create(
                    department="CSE", semester=SEMESTER, total_marks=100, total_questions=QUESTIONS, duration_minutes=60
                )
            questions = list(ExamQuestion.objects.filter(exam=exam).order_by("id"))
            for index in range(len(questions), QUESTIONS):
                questions.append(
                    ExamQuestion.objects.create(
                        exam=exam,
                        subject="Mathematics",
                        question_text=f"Demo question {index + 1}: pick A.",
                        type="option",
                        options={"A": "Right answer", "B": "Wrong answer"},
                        answer=json.dumps(["A"]),
                        marks=10,
                        semester=SEMESTER,
                        department_shortname="CSE",
                    )
                )

            now = timezone.now()
            schedule = ExamSchedule.objects.filter(exam=exam).order_by("id").first()
            if schedule is None:
                schedule = ExamSchedule.objects.create(exam=exam, start_time=now, end_time=now)
            schedule.start_time = now - timedelta(minutes=2)
            schedule.end_time = now + timedelta(hours=3)
            schedule.is_active = True
            schedule.save()

            for number, (name, (correct, flags)) in enumerate(APPLICANTS.items(), start=1):
                student, _ = Students.objects.update_or_create(
                    username=name,
                    defaults={
                        "password": STUDENT_PASSWORD,
                        "f_id": f"E2E-{number:03d}",
                        "full_name": f"Demo Applicant {number}",
                        "department_shortname": "CSE",
                        "registration_semester": SEMESTER,
                        "department_choices": [{"department_id": cse.id, "priority": 1}],
                    },
                )
                StudentAssignTeacherExam.objects.get_or_create(
                    student=student, exam=exam, defaults={"schedule": schedule, "teacher": teacher}
                )
                if correct is None or Submission.objects.filter(student=student, exam=exam).exists():
                    continue
                for index, question in enumerate(questions):
                    ok = index < correct
                    Submission.objects.create(
                        student=student, exam=exam, question=question, answer="A" if ok else "B", is_correct=ok
                    )
                if flags is not None and not ProctorSession.objects.filter(student=student, exam=exam).exists():
                    session = ProctorSession.objects.create(
                        student=student, exam=exam, token=services.secrets.token_hex(20), consent_at=now
                    )
                    for _ in range(flags):
                        services.record_flag(session, "TAB_SWITCH", {"demo": True}, None, None)
                    services.end_session(session)

        outcome = calculate_semester_admission_results(department=cse, semester=SEMESTER)
        self.stdout.write(
            f"Demo ready: exam {exam.id} ({SEMESTER}, CSE) open until {schedule.end_time:%H:%M}; "
            f"applicants {', '.join(APPLICANTS)}; results: {outcome.get('message', outcome)}"
        )
