"""
Admission result calculation helpers.

The current admission workflow needs one reusable source of truth per
department + semester, while still calculating candidate performance from a
specific exam. This service keeps that logic in one place.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from ..models import (
    AdmissionConfiguration,
    AdmissionResult,
    Department,
    DepartmentThreshold,
    Exam,
    ExamQuestion,
    MarksDistribution,
    StudentAssignTeacherExam,
    Students,
    SubjectPriority,
    Submission,
)
from ..models.viva_marks import VivaMarks
from ..utils import normalize_semester_filter
from .viva_assessment import get_viva_assessment_for_student_exam


RESULT_STATUSES = ("ACCEPTED", "SELECTED", "WAITING", "REJECTED", "ABSENT")

# weighted_total_marks is a FloatField rounded to 2 decimals (see
# round_weighted_value). A value that should equal the threshold can compare
# just below it because of binary-float representation, which flips a candidate
# SELECTED<->WAITING<->REJECTED between otherwise-identical recalculations. Give
# every threshold comparison half a rounding unit of slack so the boundary is
# stable and consistent across all comparison sites.
THRESHOLD_EPSILON = 0.005


def normalize_semester_input(value):
    normalized = normalize_semester_filter(value)
    if normalized:
        return normalized
    return str(value).strip() if value is not None else None


def get_exams_for_department_semester(department, semester):
    if not semester:
        return Exam.objects.none()

    normalized_semester = normalize_semester_input(semester)
    exams = Exam.objects.filter(semester__iexact=normalized_semester)

    if not department:
        return exams

    department_name = department.department_name.strip()
    department_shortname = department.department_shortname.strip()

    from .access_control import get_faculty_for_department
    dept_id = department.id if isinstance(department, Department) else (int(department) if str(department).isdigit() else None)
    parent_faculty = get_faculty_for_department(dept_id) if dept_id else None

    q_dept = (
        Q(department__iexact=department_name) | Q(department__iexact=department_shortname)
    )
    if parent_faculty:
        q_dept |= Q(faculty_ref=parent_faculty, exam_type__iexact="CENTRAL")

    return exams.filter(q_dept)


def get_threshold_mapping_for_semester(department, semester):
    if not department or not semester:
        return None

    normalized_semester = normalize_semester_input(semester)
    return DepartmentThreshold.objects.filter(
        department=department,
        semester__iexact=normalized_semester,
    ).first()


def is_configuration_complete(mapping):
    if not mapping:
        return False
    if mapping.seat_limit is None or mapping.seat_limit <= 0:
        return False
    if mapping.min_threshold_mark is None:
        return False
    return True


def clamp(value, minimum=0.0, maximum=None):
    value = float(value or 0.0)
    if maximum is not None:
        value = min(value, maximum)
    return max(value, minimum)


def normalize_score(score, max_score):
    if max_score <= 0:
        return 0.0
    return clamp(score, 0.0, max_score) / max_score


def round_weighted_value(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def resolve_department_for_exam(exam):
    """
    Exams store department as text, so resolve it back to a Department row.
    For Central exams without direct department text, resolve via faculty_ref departments.
    """
    dept = Department.objects.filter(
        Q(department_shortname__iexact=exam.department)
        | Q(department_name__iexact=exam.department)
    ).first()
    if dept:
        return dept
    if getattr(exam, 'faculty_ref', None):
        return exam.faculty_ref.departments.first()
    return None


def get_student_department(student):
    """
    Get the department for a student based on their department_shortname.
    """
    department = Department.objects.filter(
        department_shortname__iexact=student.department_shortname
    ).first()
    if department:
        return department

    return Department.objects.filter(
        department_name__iexact=student.department_shortname
    ).first()


def extract_subject_mark(subject_wise_marks, subject_name):
    """
    Extract the marks obtained for a subject from subject_wise_marks JSON.
    Handles various structures:
    - {"marks_obtained": 85, ...}
    - {"marks": 85, ...}
    - 85 (numeric direct value)
    Matches subject name case-insensitively as fallback.
    """
    if not isinstance(subject_wise_marks, dict) or not subject_name:
        return 0.0

    # 1. Direct key lookup
    val = subject_wise_marks.get(subject_name)

    # 2. Case-insensitive lookup if direct key not found
    if val is None:
        target = str(subject_name).strip().lower()
        for k, v in subject_wise_marks.items():
            if str(k).strip().lower() == target:
                val = v
                break

    if val is None:
        return 0.0

    if isinstance(val, dict):
        mark = val.get("marks_obtained", val.get("marks", val.get("score", 0.0)))
        try:
            return float(mark)
        except (ValueError, TypeError):
            return 0.0
    elif isinstance(val, (int, float)):
        return float(val)
    elif isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0


def get_priority_subject_names_for_department(department):
    """
    Returns ordered list of subject names for the given department,
    from highest priority (priority 1) to lowest priority.
    """
    if not department:
        return []

    dept_id = None
    if isinstance(department, Department):
        dept_id = department.id
    elif isinstance(department, int):
        dept_id = department
    elif isinstance(department, str):
        if department.isdigit():
            dept_id = int(department)
        else:
            dept = Department.objects.filter(
                Q(department_shortname__iexact=department)
                | Q(department_name__iexact=department)
            ).first()
            if dept:
                dept_id = dept.id

    if not dept_id:
        return []

    priorities = (
        SubjectPriority.objects.filter(department_id=dept_id)
        .select_related("subject")
        .order_by("priority")
    )
    return [p.subject.subject_name for p in priorities if p.subject]


def build_candidate_tiebreak_key(candidate, priority_subject_names=None):
    """
    Constructs a deterministic tuple key for candidate ranking and tie-breaking.
    1. weighted_total_marks (descending): Higher total marks always ranks higher.
    2. Sequential subject priority comparison:
       Compare subject marks in priority order (1st priority, 2nd, 3rd, ...).
       The candidate with higher marks in the first subject where marks differ ranks higher.
    3. Fallback tie-breaking:
       If total marks and all priority subject marks are identical,
       fall back to written_viva_total (descending), then mcq_marks (descending),
       and finally student_id (ascending deterministic).
    """
    priority_subject_names = priority_subject_names or []
    subject_scores = tuple(
        -round(extract_subject_mark(candidate.subject_wise_marks, s_name), 4)
        for s_name in priority_subject_names
    )

    return (
        -round(float(candidate.weighted_total_marks or 0.0), 4),
        *subject_scores,
        -round(float(candidate.written_viva_total or 0.0), 4),
        -round(float(candidate.mcq_marks or 0.0), 4),
        int(candidate.student_id or candidate.id or 0),
    )


def get_or_create_admission_configuration(exam, department):
    """
    Reuse one configuration per department + semester.

    Semester-level threshold mappings are the source of truth.
    """
    threshold_mapping = get_threshold_mapping_for_semester(department, exam.semester)

    configuration, created = AdmissionConfiguration.objects.get_or_create(
        department=department,
        semester=exam.semester,
        defaults={
            "exam": exam,
            "threshold": (
                threshold_mapping.min_threshold_mark if threshold_mapping else 0.0
            ),
            "seat_limit": (
                threshold_mapping.seat_limit if threshold_mapping else 0
            ),
            "waiting_student_limit": (
                threshold_mapping.waiting_student_limit if threshold_mapping else 0
            ),
        },
    )

    update_fields = []
    if configuration.exam_id != exam.id:
        configuration.exam = exam
        update_fields.append("exam")

    if threshold_mapping:
        if configuration.threshold != threshold_mapping.min_threshold_mark:
            configuration.threshold = threshold_mapping.min_threshold_mark
            update_fields.append("threshold")
        if configuration.seat_limit != threshold_mapping.seat_limit:
            configuration.seat_limit = threshold_mapping.seat_limit
            update_fields.append("seat_limit")
        if configuration.waiting_student_limit != threshold_mapping.waiting_student_limit:
            configuration.waiting_student_limit = threshold_mapping.waiting_student_limit
            update_fields.append("waiting_student_limit")

    if update_fields:
        configuration.save(update_fields=update_fields + ["updated_at"])

    return configuration


def calculate_mcq_marks_for_student(student, exam, student_submissions=None):
    """
    Calculate written marks and subject-wise breakdown for a student.
    """
    submissions = list(student_submissions or [])
    if not submissions:
        submissions = list(
            Submission.objects.filter(student=student, exam=exam).select_related("question")
        )

    if not submissions:
        return 0.0, {}

    mcq_marks = 0.0
    for submission in submissions:
        if submission.is_correct:
            mcq_marks += submission.question.marks

    exam_subjects = (
        ExamQuestion.objects.filter(exam=exam)
        .values_list("subject", flat=True)
        .distinct()
    )

    subject_wise_marks = {}
    for subject_name in exam_subjects:
        subject_submissions = [sub for sub in submissions if sub.question.subject == subject_name]
        total_subject_questions = ExamQuestion.objects.filter(
            exam=exam,
            subject=subject_name,
        ).count()
        correct_subject_answers = sum(1 for sub in subject_submissions if sub.is_correct)
        subject_marks = sum(sub.question.marks for sub in subject_submissions if sub.is_correct)

        subject_wise_marks[subject_name] = {
            "total_questions": total_subject_questions,
            "correct_answers": correct_subject_answers,
            "marks_obtained": subject_marks,
            "percentage": (
                correct_subject_answers / total_subject_questions * 100
                if total_subject_questions > 0
                else 0
            ),
        }

    return mcq_marks, subject_wise_marks


def get_viva_marks_for_student(student):
    try:
        viva_marks = VivaMarks.objects.get(student=student)
        return float(viva_marks.marks)
    except VivaMarks.DoesNotExist:
        return 0.0


def get_viva_marks_for_student_exam(student, exam):
    viva_assignment = get_viva_assessment_for_student_exam(student, exam)
    if viva_assignment:
        return float(viva_assignment.total_marks or 0)
    return get_viva_marks_for_student(student)


def get_academic_score(student):
    diploma_score = clamp(student.diploma)
    hsc_score = clamp(student.hsc)
    academic_type = str(getattr(student, "academic_type", "") or "").upper()

    if academic_type == "DIPLOMA":
        return "DIPLOMA", diploma_score
    if academic_type == "HSC":
        return "HSC", hsc_score

    # Legacy fallback for records created before academic_type existed.
    if diploma_score > 0:
        return "DIPLOMA", diploma_score
    if hsc_score > 0:
        return "HSC", hsc_score
    return "NONE", 0.0


def get_distribution_for_department(department):
    if not department:
        return None
    from .access_control import get_faculty_for_department
    dept_id = department.id if isinstance(department, Department) else (int(department) if str(department).isdigit() else None)
    if dept_id:
        faculty = get_faculty_for_department(dept_id)
        if faculty:
            # 1. Faculty-wide distribution (authoritative)
            faculty_dist = MarksDistribution.objects.filter(faculty=faculty, department__isnull=True).first()
            if faculty_dist:
                return faculty_dist
            # 2. Faculty distribution scoped to this department
            dept_under_faculty_dist = MarksDistribution.objects.filter(faculty=faculty, department_id=dept_id).first()
            if dept_under_faculty_dist:
                return dept_under_faculty_dist
            # 3. Any distribution under this faculty
            any_faculty_dist = MarksDistribution.objects.filter(faculty=faculty).first()
            if any_faculty_dist:
                return any_faculty_dist
    return MarksDistribution.objects.filter(department=department).first()


def get_academic_max_score(academic_source):
    if academic_source == "DIPLOMA":
        return 4.0
    if academic_source == "HSC":
        return 5.0
    return 0.0


def get_written_total_marks_for_exam(exam):
    total_marks = ExamQuestion.objects.filter(exam=exam).aggregate(
        total=Sum("marks")
    )["total"] or 0
    if total_marks > 0:
        return float(total_marks)
    return float(exam.total_marks or 0)


def get_viva_total_marks_for_student_exam(student, exam):
    viva_assignment = get_viva_assessment_for_student_exam(student, exam)
    if viva_assignment:
        rubric_snapshot = viva_assignment.rubric_snapshot or []
        rubric_total = sum(float(rubric.get("max_marks") or 0) for rubric in rubric_snapshot)
        if rubric_total > 0:
            return rubric_total

    # Fallback 1: Sum of VivaRubrics for student's department or parent faculty
    from .access_control import get_faculty_for_department
    from ..models.viva_rubrics import VivaRubrics
    dept = get_student_department(student) or resolve_department_for_exam(exam)
    if dept:
        faculty = get_faculty_for_department(dept.id)
        if faculty:
            faculty_rubric_total = VivaRubrics.objects.filter(faculty=faculty).aggregate(total=Sum("marks"))["total"]
            if faculty_rubric_total and faculty_rubric_total > 0:
                return float(faculty_rubric_total)
        dept_rubric_total = VivaRubrics.objects.filter(department=dept).aggregate(total=Sum("marks"))["total"]
        if dept_rubric_total and dept_rubric_total > 0:
            return float(dept_rubric_total)

    # Fallback 2: Marks distribution viva component
    distribution = get_distribution_for_department(dept) if dept else None
    if distribution and distribution.viva_marks > 0:
        return float(distribution.viva_marks)

    return 20.0


def calculate_weighted_scores(student, exam, department, mcq_marks, viva_marks):
    """
    Turn raw scores into the weighted total described by marks distribution.
    """
    distribution = get_distribution_for_department(department)
    academic_source, academic_score = get_academic_score(student)
    ssc_score = clamp(student.ssc)
    written_total_marks = get_written_total_marks_for_exam(exam)
    viva_total_marks = get_viva_total_marks_for_student_exam(student, exam)

    if not distribution:
        return {
            "ssc_score": ssc_score,
            "academic_score": academic_score,
            "academic_source": academic_source,
            "ssc_contribution": 0.0,
            "academic_contribution": 0.0,
            "written_contribution": 0.0,
            "viva_contribution": 0.0,
            "weighted_total_marks": round_weighted_value(clamp(mcq_marks + viva_marks)),
            "written_total_marks": round_weighted_value(written_total_marks),
            "viva_total_marks": round_weighted_value(viva_total_marks),
            "distribution_found": False,
        }

    ssc_contribution = normalize_score(ssc_score, 5.0) * distribution.ssc
    if academic_source == "DIPLOMA":
        academic_weight = getattr(distribution, "diploma", 0) or distribution.hsc
    elif academic_source == "HSC":
        academic_weight = distribution.hsc
    else:
        academic_weight = 0

    academic_contribution = normalize_score(
        academic_score,
        get_academic_max_score(academic_source),
    ) * academic_weight
    written_contribution = (
        normalize_score(mcq_marks, written_total_marks) * distribution.main_marks
    )
    viva_contribution = normalize_score(viva_marks, viva_total_marks) * distribution.viva_marks
    weighted_total_marks = (
        ssc_contribution
        + academic_contribution
        + written_contribution
        + viva_contribution
    )

    return {
        "ssc_score": round_weighted_value(ssc_score),
        "academic_score": round_weighted_value(academic_score),
        "academic_source": academic_source,
        "ssc_contribution": round_weighted_value(ssc_contribution),
        "academic_contribution": round_weighted_value(academic_contribution),
        "written_contribution": round_weighted_value(written_contribution),
        "viva_contribution": round_weighted_value(viva_contribution),
        "weighted_total_marks": round_weighted_value(weighted_total_marks),
        "written_total_marks": round_weighted_value(written_total_marks),
        "viva_total_marks": round_weighted_value(viva_total_marks),
        "distribution_found": True,
    }


def determine_result_status(
    attended_exam,
    is_above_threshold,
    existing_result=None,
    is_override_accepted=False,
    has_semester_submission=False,
):
    if is_override_accepted:
        return "SELECTED"
    if not attended_exam:
        # A student is ABSENT only when they sat NO exam in the semester. If they
        # submitted a different exam, this non-attended row is a stray duplicate;
        # return None so the caller skips/removes it instead of storing ABSENT.
        if has_semester_submission:
            return None
        return "ABSENT"
    if not is_above_threshold:
        return "REJECTED"
    return "WAITING"


def student_ids_with_semester_submission(exams):
    """
    Student IDs that submitted at least one of the given exams. Used to enforce
    "one exam per student per semester": a student who sat any exam in the
    semester is never treated as an absentee for a different (stray) exam.
    """
    return set(
        Submission.objects.filter(exam__in=exams)
        .values_list("student_id", flat=True)
        .distinct()
    )


def has_semester_submission(student, department, semester):
    """True when the student submitted any exam in the department + semester."""
    semester_exams = get_exams_for_department_semester(department, semester)
    return Submission.objects.filter(student=student, exam__in=semester_exams).exists()


def _result_survivor_rank(result):
    # Best survivor first: attended over absent, then higher weighted total,
    # then the most recently created row.
    return (
        1 if result.attended_exam else 0,
        result.weighted_total_marks or 0.0,
        result.created_at,
    )


def collapse_duplicate_semester_results(exams):
    """
    Enforce one AdmissionResult per student per semester, regardless of HOW a
    duplicate arose — legacy pre-guardrail dual assignments, a future guardrail
    edge case, or a manual DB edit. For each student holding more than one row
    across the semester's exams, keep the best row (attended over absent, then
    higher weighted total, then newest) and delete the rest, folding any
    admitted / override seat onto the survivor so no accepted candidate is lost.

    This is the last line of defence: even if a bad duplicate slips past every
    upstream guard, it can never surface on the board because the very next
    recalc collapses it. Returns the number of rows deleted.
    """
    grouped = defaultdict(list)
    for result in AdmissionResult.objects.filter(exam__in=exams):
        grouped[result.student_id].append(result)

    deleted = 0
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        rows.sort(key=_result_survivor_rank, reverse=True)
        survivor, losers = rows[0], rows[1:]

        had_admitted = any(r.is_admitted for r in rows)
        had_override = any(r.is_override_accepted for r in rows)
        changed = False
        if had_admitted and not survivor.is_admitted:
            survivor.is_admitted = True
            changed = True
        if had_override and not survivor.is_override_accepted:
            survivor.is_override_accepted = True
            changed = True
        if (survivor.is_admitted or survivor.is_override_accepted) and not survivor.is_selected:
            survivor.is_selected = True
            survivor.result_status = "SELECTED"
            changed = True
        if changed:
            survivor.save()

        for loser in losers:
            loser.delete()
            deleted += 1
    return deleted


def get_candidate_students_for_exam(exam):
    """
    Include assigned candidates only after their schedule has ended, while
    always keeping students who have already submitted answers.

    A student may sit only one exam per semester, so an assigned-but-not-yet-
    submitted student is pulled in as an absentee candidate only when they have
    NO submission for any exam in the same department + semester. This stops a
    student who already sat exam A from being manufactured into a duplicate
    ABSENT row for a stray exam B in the same semester.
    """
    now = timezone.now()
    department = resolve_department_for_exam(exam)
    semester_exams = get_exams_for_department_semester(department, exam.semester)
    semester_submitter_ids = student_ids_with_semester_submission(semester_exams)

    assigned_absentees = Students.objects.filter(
        assigned_exams__exam=exam,
        assigned_exams__schedule__end_time__lte=now,
    ).exclude(id__in=semester_submitter_ids)
    submitted_this_exam = Students.objects.filter(submissions__exam=exam)

    return (submitted_this_exam | assigned_absentees).distinct()


def summarize_status_counts(results_queryset):
    # ACCEPTED is a virtual status: admitted rows keep result_status=SELECTED
    # but are reported (and tabbed) separately from not-yet-admitted selected.
    counts = {status: 0 for status in RESULT_STATUSES}
    for status_value, is_admitted in results_queryset.values_list("result_status", "is_admitted"):
        if is_admitted:
            counts["ACCEPTED"] += 1
        elif status_value in counts:
            counts[status_value] += 1
    return counts


def is_student_linked_to_exam(student, exam):
    return StudentAssignTeacherExam.objects.filter(
        exam=exam,
        student=student,
    ).exists() or Submission.objects.filter(
        exam=exam,
        student=student,
    ).exists()


def recalculate_admission_result_record(
    *,
    exam,
    student,
    exam_department=None,
    configuration=None,
    existing_result=None,
    student_submissions=None,
    threshold_value=None,
):
    exam_department = exam_department or resolve_department_for_exam(exam)
    if not exam_department:
        return {
            "success": False,
            "error": f"Department '{exam.department}' could not be resolved for exam {exam.id}",
        }

    configuration = configuration or get_or_create_admission_configuration(exam, exam_department)
    if threshold_value is None:
        return {
            "success": False,
            "error": (
                f"No semester threshold set for {exam_department.department_name} "
                f"({exam.semester}). Please configure threshold first."
            ),
        }

    submissions = list(student_submissions or [])
    if not submissions:
        submissions = list(
            Submission.objects.filter(student=student, exam=exam).select_related("question")
        )

    attended_exam = len(submissions) > 0
    student_department = get_student_department(student) or exam_department
    mcq_marks, subject_wise_marks = calculate_mcq_marks_for_student(
        student,
        exam,
        student_submissions=submissions,
    )
    viva_marks = get_viva_marks_for_student_exam(student, exam) if attended_exam else 0.0
    weighted = calculate_weighted_scores(
        student=student,
        exam=exam,
        department=student_department,
        mcq_marks=mcq_marks,
        viva_marks=viva_marks,
    )

    is_above_threshold = attended_exam and (
        weighted["weighted_total_marks"] >= float(threshold_value) - THRESHOLD_EPSILON
    )
    override_locked = bool(
        existing_result
        and (existing_result.is_override_accepted or existing_result.is_admitted)
    )
    # Only a non-attended, non-protected row can be a stray semester duplicate,
    # so pay for the semester-submission lookup only in that case.
    student_has_semester_submission = (
        not attended_exam
        and not override_locked
        and has_semester_submission(student, exam_department, exam.semester)
    )
    result_status = determine_result_status(
        attended_exam=attended_exam,
        is_above_threshold=is_above_threshold,
        existing_result=existing_result,
        is_override_accepted=override_locked,
        has_semester_submission=student_has_semester_submission,
    )

    if result_status is None:
        # Student sat another exam this semester; a non-attended row for THIS
        # exam is a stray duplicate. Remove any existing one and create none, so
        # exactly one row per student per semester survives.
        AdmissionResult.objects.filter(exam=exam, student=student).delete()
        return {
            "success": True,
            "result": None,
            "skipped": True,
            "distribution_found": weighted["distribution_found"],
            "warning": None,
        }

    preserved_status = existing_result.status if existing_result else "PENDING"

    admission_result, _ = AdmissionResult.objects.update_or_create(
        exam=exam,
        student=student,
        defaults={
            "configuration": configuration,
            "department": student_department,
            "mcq_marks": round(mcq_marks, 2),
            "viva_marks": round(viva_marks, 2),
            "written_viva_total": round(mcq_marks + viva_marks, 2),
            "total_marks": round(mcq_marks + viva_marks, 2),
            "weighted_total_marks": weighted["weighted_total_marks"],
            "attended_exam": attended_exam,
            "subject_wise_marks": subject_wise_marks,
            "is_selected": override_locked,
            "result_status": result_status,
            "threshold_applied": float(threshold_value),
            "status": preserved_status,
            "ssc_score": weighted["ssc_score"],
            "academic_score": weighted["academic_score"],
            "academic_source": weighted["academic_source"],
            "ssc_contribution": weighted["ssc_contribution"],
            "academic_contribution": weighted["academic_contribution"],
            "written_contribution": weighted["written_contribution"],
            "viva_contribution": weighted["viva_contribution"],
        },
    )

    return {
        "success": True,
        "result": admission_result,
        "distribution_found": weighted["distribution_found"],
        "warning": (
            f"Marks distribution not found for department "
            f"'{student_department.department_name}'. Weighted total fell back "
            f"to raw written + viva for student {student.username}."
            if not weighted["distribution_found"]
            else None
        ),
    }


def apply_semester_result_statuses(
    *,
    department,
    semester,
    threshold_value,
    seat_limit,
    waiting_student_limit=0,
):
    if threshold_value is None or seat_limit is None or seat_limit <= 0:
        return {
            "success": False,
            "configuration_missing": True,
            "error": "Threshold or seat limit is not set for this semester.",
        }

    exams = list(get_exams_for_department_semester(department, semester))
    if not exams:
        return {
            "success": False,
            "configuration_missing": False,
            "error": "No exams found for the selected semester.",
        }

    threshold_value = float(threshold_value)

    # Collapse any duplicate rows to one per student BEFORE ranking, so a
    # duplicate can never surface no matter how it was created (see
    # collapse_duplicate_semester_results).
    collapse_duplicate_semester_results(exams)

    results = AdmissionResult.objects.filter(exam__in=exams)

    results.update(threshold_applied=threshold_value, is_selected=False)

    # Admitted candidates hold their seats exactly like override-accepted ones:
    # forced SELECTED and counted against seat_limit before natural selection.
    protected_qs = results.filter(Q(is_override_accepted=True) | Q(is_admitted=True))
    protected_qs.exclude(result_status="SELECTED").update(result_status="SELECTED")
    protected_qs.update(is_selected=True)
    protected_count = protected_qs.count()

    non_override = results.filter(is_override_accepted=False, is_admitted=False)

    # One exam per student per semester: a non-attended row for a student who
    # submitted a DIFFERENT exam this semester is a stray duplicate. Delete it
    # (rather than stamping ABSENT) so the same student never appears twice, and
    # a student who sat an exam is never wrongly shown as absent.
    semester_submitter_ids = student_ids_with_semester_submission(exams)
    non_override.filter(
        attended_exam=False,
        student_id__in=semester_submitter_ids,
    ).delete()

    non_override.filter(attended_exam=False).update(result_status="ABSENT")
    non_override.filter(attended_exam=True).update(result_status="REJECTED")

    priority_subject_names = get_priority_subject_names_for_department(department)

    qualified_qs = non_override.filter(
        attended_exam=True,
        weighted_total_marks__gte=threshold_value - THRESHOLD_EPSILON,
    )
    qualified_candidates = list(qualified_qs)
    qualified_candidates.sort(
        key=lambda c: build_candidate_tiebreak_key(c, priority_subject_names)
    )

    remaining_seats = max(seat_limit - protected_count, 0)
    accepted_ids = [c.id for c in qualified_candidates[:remaining_seats]]

    if accepted_ids:
        non_override.filter(id__in=accepted_ids).update(
            result_status="SELECTED",
            is_selected=True,
        )

    # Waiting list honours the same threshold as selection: below-threshold
    # candidates are never promoted to WAITING.
    waiting_candidates_qs = non_override.filter(
        attended_exam=True,
        weighted_total_marks__gte=threshold_value - THRESHOLD_EPSILON,
    ).exclude(id__in=accepted_ids)

    waiting_candidates = list(waiting_candidates_qs)
    waiting_candidates.sort(
        key=lambda c: build_candidate_tiebreak_key(c, priority_subject_names)
    )
    waiting_limit = max(int(waiting_student_limit or 0), 0)
    waiting_ids = [c.id for c in waiting_candidates[:waiting_limit]]

    if waiting_ids:
        non_override.filter(id__in=waiting_ids).update(
            result_status="WAITING",
            is_selected=False,
        )

    return {
        "success": True,
        "configuration_missing": False,
        "override_count": protected_count,
    }


def calculate_semester_admission_results(*, department, semester):
    threshold_mapping = get_threshold_mapping_for_semester(department, semester)
    if not is_configuration_complete(threshold_mapping):
        return {
            "success": False,
            "processed_count": 0,
            "selected_count": 0,
            "not_selected_count": 0,
            "configuration_missing": True,
            "errors": [
                "Threshold or seat limit is not set for this semester."
            ],
        }

    exams = list(get_exams_for_department_semester(department, semester))
    if not exams:
        return {
            "success": False,
            "processed_count": 0,
            "selected_count": 0,
            "not_selected_count": 0,
            "configuration_missing": False,
            "errors": ["No exams found for the selected semester"],
        }

    processed_count = 0
    errors = []
    configuration_id = None

    with transaction.atomic():
        for exam in exams:
            configuration = get_or_create_admission_configuration(exam, department)
            configuration_id = configuration.id

            candidates = list(get_candidate_students_for_exam(exam))
            if not candidates:
                continue

            submissions = Submission.objects.filter(exam=exam).select_related(
                "student",
                "question",
            )
            submissions_by_student = defaultdict(list)
            for submission in submissions:
                submissions_by_student[submission.student_id].append(submission)

            existing_results = {
                result.student_id: result
                for result in AdmissionResult.objects.filter(exam=exam)
            }

            for student in candidates:
                try:
                    student_submissions = submissions_by_student.get(student.id, [])
                    existing_result = existing_results.get(student.id)
                    recalculated = recalculate_admission_result_record(
                        exam=exam,
                        student=student,
                        exam_department=department,
                        configuration=configuration,
                        existing_result=existing_result,
                        student_submissions=student_submissions,
                        threshold_value=threshold_mapping.min_threshold_mark,
                    )
                    if not recalculated["success"]:
                        raise ValueError(recalculated["error"])
                    if recalculated.get("warning"):
                        errors.append(recalculated["warning"])

                    processed_count += 1
                except Exception as exc:
                    errors.append(
                        f"Error processing student {student.username} (ID: {student.id}): {exc}"
                    )

    status_application = apply_semester_result_statuses(
        department=department,
        semester=semester,
        threshold_value=threshold_mapping.min_threshold_mark,
        seat_limit=threshold_mapping.seat_limit,
        waiting_student_limit=threshold_mapping.waiting_student_limit,
    )
    if not status_application.get("success"):
        return {
            "success": False,
            "processed_count": processed_count,
            "selected_count": 0,
            "not_selected_count": 0,
            "configuration_missing": status_application.get("configuration_missing", False),
            "errors": [status_application.get("error", "Failed to apply result statuses")],
        }

    refreshed_results = AdmissionResult.objects.filter(exam__in=exams)
    status_counts = summarize_status_counts(refreshed_results)

    return {
        "success": True,
        "processed_count": processed_count,
        "selected_count": status_counts["SELECTED"],
        "not_selected_count": (
            status_counts["WAITING"]
            + status_counts["REJECTED"]
            + status_counts["ABSENT"]
        ),
        "status_counts": status_counts,
        "configuration_id": configuration_id,
        "configuration_missing": False,
        "errors": errors,
    }


def calculate_admission_results(exam_id):
    """
    Calculate or refresh all admission results for an exam.
    """
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return {
            "success": False,
            "processed_count": 0,
            "selected_count": 0,
            "not_selected_count": 0,
            "configuration_missing": False,
            "errors": [f"Exam with ID {exam_id} does not exist"],
        }

    exam_department = resolve_department_for_exam(exam)
    if not exam_department:
        return {
            "success": False,
            "processed_count": 0,
            "selected_count": 0,
            "not_selected_count": 0,
            "configuration_missing": False,
            "errors": [f"Department '{exam.department}' could not be resolved for exam {exam_id}"],
        }

    result = calculate_semester_admission_results(
        department=exam_department,
        semester=exam.semester,
    )
    result["exam_id"] = exam_id
    return result


def recalculate_single_student_result(exam_id, student_id):
    try:
        exam = Exam.objects.get(id=exam_id)
        student = Students.objects.get(id=student_id)
    except (Exam.DoesNotExist, Students.DoesNotExist) as exc:
        return {
            "success": False,
            "error": str(exc),
        }

    exam_department = resolve_department_for_exam(exam)
    if not exam_department:
        return {
            "success": False,
            "error": f"Department '{exam.department}' could not be resolved for exam {exam_id}",
        }

    threshold_mapping = get_threshold_mapping_for_semester(exam_department, exam.semester)
    if not is_configuration_complete(threshold_mapping):
        return {
            "success": False,
            "configuration_missing": True,
            "error": "Threshold or seat limit is not set for this semester.",
        }

    if not is_student_linked_to_exam(student, exam):
        return {
            "success": False,
            "error": f"Student {student.username} is not linked to exam {exam_id}",
        }

    existing_result = AdmissionResult.objects.filter(exam_id=exam_id, student_id=student_id).first()
    configuration = get_or_create_admission_configuration(exam, exam_department)
    result = recalculate_admission_result_record(
        exam=exam,
        student=student,
        exam_department=exam_department,
        configuration=configuration,
        existing_result=existing_result,
        threshold_value=threshold_mapping.min_threshold_mark,
    )
    if not result["success"]:
        return result

    status_application = apply_semester_result_statuses(
        department=exam_department,
        semester=exam.semester,
        threshold_value=threshold_mapping.min_threshold_mark,
        seat_limit=threshold_mapping.seat_limit,
        waiting_student_limit=threshold_mapping.waiting_student_limit,
    )
    if not status_application.get("success"):
        return {
            "success": False,
            "configuration_missing": status_application.get("configuration_missing", False),
            "error": status_application.get("error", "Failed to refresh result statuses"),
        }

    # The row may have been removed as a stray semester duplicate (student sat a
    # different exam this semester), so re-fetch instead of trusting the
    # pre-recalc object and report a graceful skip when it is gone.
    admission_result = AdmissionResult.objects.filter(
        exam_id=exam_id, student_id=student_id
    ).first()
    if admission_result is None:
        return {
            "success": True,
            "student": student.username,
            "student_id": student.id,
            "exam_id": exam.id,
            "action": "skipped",
            "result_status": None,
            "warning": result.get("warning"),
        }

    return {
        "success": True,
        "student": student.username,
        "student_id": student.id,
        "exam_id": exam.id,
        "viva_marks": admission_result.viva_marks,
        "total_marks": admission_result.total_marks,
        "weighted_total_marks": admission_result.weighted_total_marks,
        "is_selected": admission_result.is_selected,
        "result_status": admission_result.result_status,
        "viva_contribution": admission_result.viva_contribution,
        "action": "updated",
        "warning": result.get("warning"),
    }
