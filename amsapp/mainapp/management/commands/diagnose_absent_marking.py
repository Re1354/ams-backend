from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from mainapp.models import AdmissionResult, Department, Exam, StudentAssignTeacherExam
from mainapp.services.admission_calculator import (
    get_threshold_mapping_for_semester,
    is_configuration_complete,
)
from mainapp.utils import normalize_semester_filter


class Command(BaseCommand):
    help = (
        "Read-only report of the data states that block absent-marking: "
        "cross-semester assignments, ended assignments with no admission result, "
        "and department/semester pairs without a complete threshold configuration."
    )

    def add_arguments(self, parser):
        parser.add_argument("--semester", help="Only inspect exams in this semester")
        parser.add_argument("--department", help="Only inspect exams of this department (shortname or full name)")
        parser.add_argument("--limit", type=int, default=50, help="Max rows printed per section (counts are always full)")

    def handle(self, *args, **options):
        semester_filter = normalize_semester_filter(options.get("semester"))
        department_filter = (options.get("department") or "").strip()
        limit = max(options["limit"], 0)
        now = timezone.now()

        assignments = StudentAssignTeacherExam.objects.select_related("student", "exam", "schedule")
        if department_filter:
            assignments = assignments.filter(
                Q(exam__department__iexact=department_filter)
                | Q(exam__department__iexact=self._resolve_department_name(department_filter))
            )

        def in_semester_scope(exam):
            if not semester_filter:
                return True
            return normalize_semester_filter(exam.semester) == semester_filter

        # Section 1: assignments whose student registration semester differs from the exam semester.
        cross_semester = [
            assignment
            for assignment in assignments
            if in_semester_scope(assignment.exam)
            and normalize_semester_filter(assignment.student.registration_semester)
            != normalize_semester_filter(assignment.exam.semester)
        ]
        self._print_section_header("1. Cross-semester assignments", len(cross_semester))
        for assignment in cross_semester[:limit]:
            self.stdout.write(
                f"  assignment={assignment.id} student={assignment.student.username} "
                f"(f_id={assignment.student.f_id}, semester={assignment.student.registration_semester!r}) "
                f"exam={assignment.exam_id} (semester={assignment.exam.semester!r}) "
                f"schedule_end={assignment.schedule.end_time if assignment.schedule_id else None}"
            )

        # Section 2: assignments past their schedule end with no AdmissionResult row —
        # the direct "should be ABSENT but nothing exists" symptom. Same query shape as
        # ensure_semester_admission_results in views/admission_results.py.
        missing_results = assignments.filter(schedule__end_time__lte=now).exclude(
            Exists(
                AdmissionResult.objects.filter(
                    exam_id=OuterRef("exam_id"),
                    student_id=OuterRef("student_id"),
                )
            )
        )
        missing_results = [a for a in missing_results if in_semester_scope(a.exam)]
        self._print_section_header("2. Ended assignments with no AdmissionResult row", len(missing_results))
        missing_pairs = set()
        for assignment in missing_results:
            missing_pairs.add(
                (assignment.exam.department, normalize_semester_filter(assignment.exam.semester))
            )
        for assignment in missing_results[:limit]:
            self.stdout.write(
                f"  assignment={assignment.id} student={assignment.student.username} "
                f"(f_id={assignment.student.f_id}) exam={assignment.exam_id} "
                f"(department={assignment.exam.department!r}, semester={assignment.exam.semester!r}) "
                f"schedule_end={assignment.schedule.end_time}"
            )

        # Section 3: exam department/semester pairs where result generation is silently
        # blocked — either the department string resolves to no Department row, or no
        # complete DepartmentThreshold exists for the exam's semester.
        exam_pairs = Exam.objects.values_list("department", "semester").distinct()
        unresolved = []
        unconfigured = []
        for department_text, semester in exam_pairs:
            normalized_semester = normalize_semester_filter(semester)
            if semester_filter and normalized_semester != semester_filter:
                continue
            if department_filter and department_text.strip().lower() not in {
                department_filter.lower(),
                self._resolve_department_name(department_filter).lower(),
            }:
                continue
            department = Department.objects.filter(
                Q(department_shortname__iexact=department_text)
                | Q(department_name__iexact=department_text)
            ).first()
            if not department:
                unresolved.append((department_text, semester))
                continue
            mapping = get_threshold_mapping_for_semester(department, semester)
            if not is_configuration_complete(mapping):
                explains_missing = (department_text, normalized_semester) in missing_pairs
                unconfigured.append((department_text, semester, explains_missing))

        self._print_section_header(
            "3. Blocked department/semester pairs", len(unresolved) + len(unconfigured)
        )
        for department_text, semester in unresolved[:limit]:
            self.stdout.write(
                f"  UNRESOLVED DEPARTMENT: exam department {department_text!r} (semester={semester!r}) "
                "matches no Department row — results cannot be calculated for these exams"
            )
        for department_text, semester, explains_missing in unconfigured[:limit]:
            note = " <-- explains missing ABSENT rows in section 2" if explains_missing else ""
            self.stdout.write(
                f"  NO THRESHOLD CONFIG: department={department_text!r} semester={semester!r} "
                f"has no complete DepartmentThreshold (threshold + seat_limit > 0){note}"
            )

        total_issues = len(cross_semester) + len(missing_results) + len(unresolved) + len(unconfigured)
        if total_issues:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {len(cross_semester)} cross-semester assignment(s), "
                    f"{len(missing_results)} missing result row(s), "
                    f"{len(unresolved) + len(unconfigured)} blocked department/semester pair(s)."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("No absent-marking blockers found."))

    def _print_section_header(self, title, count):
        self.stdout.write(f"\n{title}: {count}")

    def _resolve_department_name(self, shortname):
        department = Department.objects.filter(department_shortname__iexact=shortname).first()
        return department.department_name if department else shortname
