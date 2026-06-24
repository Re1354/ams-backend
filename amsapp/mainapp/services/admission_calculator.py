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
    Submission,
)
from ..models.viva_marks import VivaMarks
from ..utils import normalize_semester_filter
from .viva_assessment import get_viva_assessment_for_student_exam


RESULT_STATUSES = ("SELECTED", "WAITING", "REJECTED", "ABSENT")


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
    return exams.filter(
        Q(department__iexact=department_name) | Q(department__iexact=department_shortname)
    )


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
    """
    return Department.objects.filter(
        Q(department_shortname__iexact=exam.department)
        | Q(department_name__iexact=exam.department)
    ).first()


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
    if not viva_assignment:
        return 0.0

    rubric_snapshot = viva_assignment.rubric_snapshot or []
    rubric_total = 0.0
    for rubric in rubric_snapshot:
        rubric_total += float(rubric.get("max_marks") or 0)
    return rubric_total


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
    academic_weight = distribution.hsc if academic_source in {"HSC", "DIPLOMA"} else 0
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
):
    if is_override_accepted:
        return "SELECTED"
    if not attended_exam:
        return "ABSENT"
    if not is_above_threshold:
        return "REJECTED"
    return "WAITING"


def get_candidate_students_for_exam(exam):
    """
    Include assigned candidates only after their schedule has ended, while
    always keeping students who have already submitted answers.
    """
    now = timezone.now()
    return Students.objects.filter(
        Q(assigned_exams__exam=exam, assigned_exams__schedule__end_time__lte=now)
        | Q(submissions__exam=exam)
    ).distinct()


def summarize_status_counts(results_queryset):
    counts = {status: 0 for status in RESULT_STATUSES}
    for item in results_queryset.values_list("result_status", flat=True):
        if item in counts:
            counts[item] += 1
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
        weighted["weighted_total_marks"] >= float(threshold_value)
    )
    override_locked = bool(existing_result and existing_result.is_override_accepted)
    result_status = determine_result_status(
        attended_exam=attended_exam,
        is_above_threshold=is_above_threshold,
        existing_result=existing_result,
        is_override_accepted=override_locked,
    )
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
    results = AdmissionResult.objects.filter(exam__in=exams)

    results.update(threshold_applied=threshold_value, is_selected=False)

    override_qs = results.filter(is_override_accepted=True)
    override_qs.exclude(result_status="SELECTED").update(result_status="SELECTED")
    override_qs.update(is_selected=True)
    override_count = override_qs.count()

    non_override = results.filter(is_override_accepted=False)
    non_override.filter(attended_exam=False).update(result_status="ABSENT")
    non_override.filter(attended_exam=True).update(result_status="REJECTED")

    qualified = non_override.filter(
        attended_exam=True,
        weighted_total_marks__gte=threshold_value,
    ).order_by(
        "-weighted_total_marks",
        "-written_viva_total",
        "-mcq_marks",
        "student_id",
    )

    remaining_seats = max(seat_limit - override_count, 0)
    accepted_ids = list(qualified.values_list("id", flat=True)[:remaining_seats])

    if accepted_ids:
        non_override.filter(id__in=accepted_ids).update(
            result_status="SELECTED",
            is_selected=True,
        )

    waiting_candidates = non_override.filter(attended_exam=True).exclude(id__in=accepted_ids).order_by(
        "-weighted_total_marks",
        "-written_viva_total",
        "-mcq_marks",
        "student_id",
    )
    waiting_limit = max(int(waiting_student_limit or 0), 0)
    waiting_ids = list(waiting_candidates.values_list("id", flat=True)[:waiting_limit])

    if waiting_ids:
        non_override.filter(id__in=waiting_ids).update(
            result_status="WAITING",
            is_selected=False,
        )

    return {
        "success": True,
        "configuration_missing": False,
        "override_count": override_count,
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

    admission_result = result["result"]

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

    admission_result.refresh_from_db()

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
