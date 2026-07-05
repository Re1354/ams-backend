from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import io
import os
from pathlib import Path
import re
import sys
import zipfile

from django.contrib.staticfiles import finders
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    renderer_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema

from ..authentication import CustomJWTAuthentication
from ..models import (
    AdmissionConfiguration,
    AdmissionResult,
    DepartmentThreshold,
    Exam,
    ExamQuestion,
    MarksDistribution,
    StudentAssignTeacherExam,
    Students,
    Submission,
)
from ..serializers.admission_report import StudentAdmissionDetailReportSerializer
from ..services.admission_calculator import (
    calculate_mcq_marks_for_student,
    calculate_weighted_scores,
    get_student_department,
    resolve_department_for_exam,
)
from ..services.viva_assessment import (
    build_viva_rubric_rows,
    get_viva_assessment_for_student_exam,
)
from ..utils import (
    calculate_submission_summary,
    get_correct_option_answers_display,
    get_question_options,
    resolve_submitted_option_key,
)


RESULT_STATUS_LABELS = {
    "SELECTED": "Selected",
    "WAITING": "Waiting",
    "REJECTED": "Rejected",
    "ABSENT": "Absent",
}


class PDFRenderer(BaseRenderer):
    media_type = "application/pdf"
    format = "pdf"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode("utf-8")
        return b""


class ZIPRenderer(BaseRenderer):
    media_type = "application/zip"
    format = "zip"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, str):
            return data.encode("utf-8")
        return b""

FACULTY_BY_DEPARTMENT_SHORTNAME = {
    "CSE": "Science and Information Technology",
    "SWE": "Science and Information Technology",
    "CIS": "Science and Information Technology",
    "EEE": "Engineering",
    "TE": "Engineering",
    "CE": "Engineering",
    "ME": "Engineering",
    "BBA": "Business and Entrepreneurship",
    "MBA": "Business and Entrepreneurship",
    "THM": "Business and Entrepreneurship",
    "ENG": "Humanities and Social Sciences",
    "JMC": "Humanities and Social Sciences",
    "LAW": "Humanities and Social Sciences",
    "NFE": "Health and Life Sciences",
    "PH": "Health and Life Sciences",
    "ARCH": "Health and Life Sciences",
}

FACULTY_NAME_NORMALIZERS = {
    "FSIT": "Science and Information Technology",
    "SCIENCE AND INFORMATION TECHNOLOGY": "Science and Information Technology",
    "FACULTY OF SCIENCE AND INFORMATION TECHNOLOGY": "Science and Information Technology",
    "FE": "Engineering",
    "ENGINEERING": "Engineering",
    "FACULTY OF ENGINEERING": "Engineering",
    "FEB": "Business and Entrepreneurship",
    "BUSINESS AND ENTREPRENEURSHIP": "Business and Entrepreneurship",
    "FACULTY OF BUSINESS AND ENTREPRENEURSHIP": "Business and Entrepreneurship",
    "FHS": "Humanities and Social Sciences",
    "HSS": "Humanities and Social Sciences",
    "HUMANITIES AND SOCIAL SCIENCES": "Humanities and Social Sciences",
    "FACULTY OF HUMANITIES AND SOCIAL SCIENCES": "Humanities and Social Sciences",
    "FHLS": "Health and Life Sciences",
    "HEALTH AND LIFE SCIENCES": "Health and Life Sciences",
    "FACULTY OF HEALTH AND LIFE SCIENCES": "Health and Life Sciences",
}


def format_duration(duration_minutes: int) -> str:
    if duration_minutes >= 60 and duration_minutes % 60 == 0:
        hours = duration_minutes // 60
        return f"{hours} Hour" if hours == 1 else f"{hours} Hours"
    if duration_minutes >= 60:
        hours = duration_minutes / 60
        return f"{hours:g} Hours"
    return f"{duration_minutes} Minutes"


def format_report_date(value: datetime | None = None) -> str:
    report_date = value or datetime.now()
    return report_date.strftime("%d %B %Y")


def configure_windows_weasyprint_runtime() -> None:
    if sys.platform != "win32":
        return

    os.environ.setdefault("GLIB_DISABLE_DEPRECATION_WARNINGS", "1")
    os.environ.setdefault("G_DEBUG", "")
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", "")

    candidate_directories = [
        Path(r"C:\Program Files\GTK3-Runtime Win64\bin"),
        Path(r"C:\msys64\ucrt64\bin"),
    ]

    for directory in candidate_directories:
        if not directory.exists():
            continue

        directory_text = str(directory)
        current_path = os.environ.get("PATH", "")
        if directory_text not in current_path.split(os.pathsep):
            os.environ["PATH"] = directory_text + os.pathsep + current_path

        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                add_dll_directory(directory_text)
            except OSError:
                pass


def format_report_number(value) -> str:
    if value in (None, ""):
        return "0"

    numeric_value = float(value)
    if numeric_value.is_integer():
        return str(int(numeric_value))
    return f"{numeric_value:.2f}".rstrip("0").rstrip(".")


def get_academic_source_label(final_result: dict) -> str:
    academic_source = str(final_result.get("academic_source") or "").upper()
    if academic_source == "DIPLOMA":
        return "Diploma"
    if academic_source == "HSC":
        return "HSC"
    return "Academic"


def get_academic_divisor(final_result: dict) -> float:
    academic_source = str(final_result.get("academic_source") or "").upper()
    if academic_source == "DIPLOMA":
        return 4.0
    if academic_source == "HSC":
        return 5.0
    return 0.0


def get_written_total_marks_from_report(report: dict) -> float:
    written_summary = report.get("written_summary") or {}
    return float(written_summary.get("total_marks") or 0)


def get_viva_total_marks_from_report(report: dict) -> float:
    viva = report.get("viva") or {}
    rubric_rows = viva.get("rubric_rows") or []
    return round(sum(float(row.get("max_marks") or 0) for row in rubric_rows), 2)


def build_weighted_component_equation(
    label: str,
    numerator_label: str,
    numerator_value,
    denominator_label: str,
    denominator_value,
    weight_label: str,
    weight_value,
    contribution_value,
) -> str:
    denominator_number = float(denominator_value or 0)
    if denominator_number <= 0:
        return (
            f"{label} = {weight_label} could not be applied because "
            f"{denominator_label} is 0, so contribution = "
            f"{format_report_number(contribution_value)}"
        )

    return (
        f"{label} = ({numerator_label} / {denominator_label}) × {weight_label} = "
        f"({format_report_number(numerator_value)} / {format_report_number(denominator_number)}) × "
        f"{format_report_number(weight_value)} = {format_report_number(contribution_value)}"
    )


def normalize_faculty_label(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""

    normalized = FACULTY_NAME_NORMALIZERS.get(text.upper())
    if normalized:
        return normalized

    return re.sub(r"^Faculty of\s+", "", text, flags=re.IGNORECASE).strip()


def resolve_report_faculty_name(serialized_report: dict) -> str:
    exam_faculty = normalize_faculty_label(serialized_report["written_exam"].get("faculty"))
    if exam_faculty:
        return exam_faculty

    department_shortname = str(serialized_report["student"].get("department_shortname") or "").upper()
    fallback = FACULTY_BY_DEPARTMENT_SHORTNAME.get(department_shortname)
    if fallback:
        return fallback

    return ""


def build_pdf_filename(report_data: dict) -> str:
    application_serial = str(report_data["student"].get("application_serial") or "student")
    semester = str(report_data["written_exam"].get("semester") or "semester")
    safe_serial = re.sub(r"[^a-zA-Z0-9_-]+", "-", application_serial).strip("-") or "student"
    safe_semester = re.sub(r"[^a-zA-Z0-9_-]+", "-", semester).strip("-") or "semester"
    return f"student-admission-report-{safe_serial}-{safe_semester}.pdf"


def extract_question_status_counts(question_reviews: list[dict]) -> dict[str, int]:
    status_counts = {"CORRECT": 0, "WRONG": 0, "SKIPPED": 0}
    for question in question_reviews:
        status_key = str(question.get("status") or "").upper()
        if status_key in status_counts:
            status_counts[status_key] += 1
    return status_counts


def normalize_pdf_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def format_pdf_answer_display(answer: dict | None, fallback: str) -> str:
    if not answer:
        return fallback

    key = normalize_pdf_text(answer.get("key"))
    text = normalize_pdf_text(answer.get("text"))

    if key and text:
        return f"{key}. {text}"
    if text:
        return text
    if key:
        return key
    return fallback


def format_pdf_correct_answers_display(answers: list[dict] | None) -> str:
    if not answers:
        return "Not available"

    formatted_answers = [
        format_pdf_answer_display(answer, "Not available")
        for answer in answers
        if format_pdf_answer_display(answer, "").strip()
    ]

    return ", ".join(formatted_answers) if formatted_answers else "Not available"


def enrich_question_reviews_for_pdf(question_reviews: list[dict]) -> list[dict]:
    enriched_reviews = []
    for review in question_reviews:
        next_review = {**review}
        next_review["question_text"] = normalize_pdf_text(review.get("question_text"))
        next_review["student_answer_display"] = format_pdf_answer_display(
            review.get("student_answer"),
            "Not answered",
        )
        next_review["correct_answers_display"] = format_pdf_correct_answers_display(
            review.get("correct_answers"),
        )

        options = review.get("options") or {}
        next_review["options_items"] = [
            {
                "key": normalize_pdf_text(option_key),
                "text": normalize_pdf_text(option_value),
            }
            for option_key, option_value in options.items()
        ]
        enriched_reviews.append(next_review)

    return enriched_reviews


def build_calculation_equations(report: dict) -> tuple[list[dict[str, str]], str | None]:
    final_result = report.get("final_result") or {}
    distribution = final_result.get("distribution_percentages")
    if not distribution:
        return [], (
            "Calculation formula unavailable because marks distribution percentages "
            "were not found for this report."
        )

    academic_label = get_academic_source_label(final_result)
    academic_source = str(final_result.get("academic_source") or "").upper()
    academic_divisor = get_academic_divisor(final_result)
    written_total_marks = get_written_total_marks_from_report(report)
    viva_total_marks = get_viva_total_marks_from_report(report)
    if academic_source in {"DIPLOMA", "HSC"}:
        academic_weight = distribution.get("hsc", 0)
    else:
        academic_weight = 0

    lines = [
        {
            "label": "SSC Contribution",
            "equation": build_weighted_component_equation(
                label="SSC Contribution",
                numerator_label="SSC Score",
                numerator_value=final_result.get("ssc_score"),
                denominator_label="SSC Total",
                denominator_value=5,
                weight_label="SSC Weight",
                weight_value=distribution.get("ssc"),
                contribution_value=final_result.get("ssc_contribution"),
            ),
        },
        {
            "label": f"{academic_label} Contribution",
            "equation": build_weighted_component_equation(
                label=f"{academic_label} Contribution",
                numerator_label=f"{academic_label} Score",
                numerator_value=final_result.get("academic_score"),
                denominator_label=f"{academic_label} Total",
                denominator_value=academic_divisor,
                weight_label=f"{academic_label} Weight",
                weight_value=academic_weight,
                contribution_value=final_result.get("academic_contribution"),
            ),
        },
        {
            "label": "Written Contribution",
            "equation": build_weighted_component_equation(
                label="Written Contribution",
                numerator_label="Written Marks",
                numerator_value=final_result.get("written_marks"),
                denominator_label="Total Written Marks",
                denominator_value=written_total_marks,
                weight_label="Written Weight",
                weight_value=distribution.get("written"),
                contribution_value=final_result.get("written_contribution"),
            ),
        },
        {
            "label": "Viva Contribution",
            "equation": build_weighted_component_equation(
                label="Viva Contribution",
                numerator_label="Viva Marks",
                numerator_value=final_result.get("viva_marks"),
                denominator_label="Total Viva Marks",
                denominator_value=viva_total_marks,
                weight_label="Viva Weight",
                weight_value=distribution.get("viva"),
                contribution_value=final_result.get("viva_contribution"),
            ),
        },
        {
            "label": "Final Weighted Total",
            "equation": (
                f"Final Weighted Total = SSC Contribution + {academic_label} Contribution + "
                "Written Contribution + Viva Contribution = "
                f"{format_report_number(final_result.get('ssc_contribution'))} + "
                f"{format_report_number(final_result.get('academic_contribution'))} + "
                f"{format_report_number(final_result.get('written_contribution'))} + "
                f"{format_report_number(final_result.get('viva_contribution'))} = "
                f"{format_report_number(final_result.get('weighted_total'))}"
            ),
        },
    ]

    return lines, None


def build_student_admission_pdf_context(serialized_report: dict) -> dict:
    font_path = finders.find("mainapp/fonts/HindSiliguri-Regular.ttf")
    if isinstance(font_path, (list, tuple)):
        font_path = font_path[0] if font_path else None

    logo_path = finders.find("mainapp/images/diu-logo.png")
    if isinstance(logo_path, (list, tuple)):
        logo_path = logo_path[0] if logo_path else None

    question_reviews = enrich_question_reviews_for_pdf(
        serialized_report.get("question_reviews", [])
    )
    question_status_counts = extract_question_status_counts(question_reviews)
    resolved_status = serialized_report["final_result"].get("result_status")
    calculation_equations, calculation_note = build_calculation_equations(serialized_report)

    return {
        "report": serialized_report,
        "status_labels": RESULT_STATUS_LABELS,
        "result_status_label": RESULT_STATUS_LABELS.get(resolved_status, resolved_status),
        "generated_on": format_report_date(),
        "faculty_name": resolve_report_faculty_name(serialized_report),
        "font_uri": Path(font_path).resolve().as_uri() if font_path else None,
        "logo_uri": Path(logo_path).resolve().as_uri() if logo_path else None,
        "question_status_counts": question_status_counts,
        "question_reviews": question_reviews,
        "calculation_equations": calculation_equations,
        "calculation_note": calculation_note,
    }


def render_student_admission_report_pdf_html(serialized_report: dict) -> str:
    return render_to_string(
        "admission/student_report_pdf.html",
        build_student_admission_pdf_context(serialized_report),
    )


def _build_student_admission_report_pdf_bytes(request, exam_id: int, student_id: int):
    report_data, error_payload, error_status = build_student_admission_detail_report_data(exam_id, student_id)
    if error_payload is not None:
        return None, None, error_payload, error_status

    serializer = StudentAdmissionDetailReportSerializer(report_data)
    serialized_report = serializer.data
    html = render_student_admission_report_pdf_html(serialized_report)

    try:
        configure_windows_weasyprint_runtime()
        from weasyprint import HTML
    except Exception as import_error:
        return (
            None,
            None,
            {
                "success": False,
                "message": "PDF renderer is unavailable. Verify WeasyPrint installation and system libraries.",
                "detail": str(import_error),
            },
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    except Exception as render_error:
        error_msg = str(render_error).lower()
        if "unsupported_os" in error_msg or "glib" in error_msg or "subsystem" in error_msg:
            return (
                None,
                None,
                {
                    "success": False,
                    "message": "PDF generation temporary subsystem issue. Please retry.",
                    "detail": "Windows GLib subsystem error. This is often transient.",
                },
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return (
            None,
            None,
            {
                "success": False,
                "message": "Failed to generate PDF report.",
                "detail": str(render_error),
            },
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return pdf_bytes, serialized_report, None, None


def _ensure_unique_zip_filename(existing_names: set[str], filename: str) -> str:
    if filename not in existing_names:
        existing_names.add(filename)
        return filename

    stem = filename
    extension = ""
    if "." in filename:
        stem, extension = filename.rsplit(".", 1)
        extension = f".{extension}"

    suffix = 2
    while True:
        candidate = f"{stem}-{suffix}{extension}"
        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate
        suffix += 1


def build_student_admission_detail_report_data(exam_id: int, student_id: int):
    try:
        exam = Exam.objects.get(id=exam_id)
        student = Students.objects.get(id=student_id)
    except Exam.DoesNotExist:
        return None, {
            "success": False,
            "message": "Exam not found",
        }, status.HTTP_404_NOT_FOUND
    except Students.DoesNotExist:
        return None, {
            "success": False,
            "message": "Student not found",
        }, status.HTTP_404_NOT_FOUND

    written_assignment = (
        StudentAssignTeacherExam.objects.select_related("teacher", "schedule", "exam")
        .filter(student=student, exam=exam)
        .order_by("-created_at")
        .first()
    )
    if not written_assignment or not written_assignment.schedule_id:
        return None, {
            "success": False,
            "message": "No written exam assignment or schedule found for this student and exam.",
        }, status.HTTP_404_NOT_FOUND

    questions = list(ExamQuestion.objects.filter(exam=exam).order_by("id"))
    submissions = list(
        Submission.objects.filter(student=student, exam=exam).select_related("question").order_by("question_id")
    )
    submissions_by_question = {submission.question_id: submission for submission in submissions}
    summary = calculate_submission_summary(exam, submissions)
    total_questions = len(questions)
    skipped_questions = total_questions - summary["total_questions_attempted"]

    viva_assignment = get_viva_assessment_for_student_exam(student, exam)
    subject_summary = build_subject_summary_rows(exam, questions, submissions_by_question)
    question_reviews = build_question_reviews(questions, submissions_by_question)
    final_result = build_final_result(exam, student, summary, viva_assignment)

    viva_rubric_rows = build_viva_rubric_rows(viva_assignment)
    viva_teacher = viva_assignment.teacher.username if viva_assignment and viva_assignment.teacher_id else None

    report_data = {
        "student": {
            "id": student.id,
            "username": student.username,
            "full_name": student.full_name,
            "application_serial": student.f_id,
            "email": student.email,
            "department_shortname": student.department_shortname,
            "registration_semester": student.registration_semester,
            "ssc": float(student.ssc or 0),
            "academic_type": student.academic_type,
            "hsc": float(student.hsc or 0),
            "diploma": float(student.diploma or 0),
        },
        "written_exam": {
            "exam_id": exam.id,
            "department": exam.department,
            "semester": exam.semester,
            "language": exam.language,
            "faculty": exam.faculty,
            "duration_minutes": exam.duration_minutes,
            "duration_display": format_duration(int(exam.duration_minutes or 0)),
            "schedule_start_time": written_assignment.schedule.start_time,
            "schedule_end_time": written_assignment.schedule.end_time,
            "exam_date": written_assignment.schedule.start_time.date().isoformat(),
            "assigned_teacher": written_assignment.teacher.username if written_assignment.teacher_id else None,
        },
        "written_summary": {
            "total_questions": total_questions,
            "attempted_questions": summary["total_questions_attempted"],
            "correct_answers": summary["correct_answers"],
            "wrong_answers": summary["wrong_answers"],
            "skipped_answers": skipped_questions,
            "obtained_marks": round(float(summary["obtained_marks"]), 2),
            "total_marks": round(float(summary["total_marks"]), 2),
            "score_percentage": float(summary["score_percentage"]),
            "grade": summary["grade"],
        },
        "subject_summary": subject_summary,
        "question_reviews": question_reviews,
        "viva": {
            "teacher": viva_teacher,
            "room": viva_assignment.room if viva_assignment else None,
            "scheduled_at": viva_assignment.scheduled_at if viva_assignment else None,
            "time": (
                viva_assignment.scheduled_at.time().isoformat()
                if viva_assignment and viva_assignment.scheduled_at
                else (viva_assignment.time.isoformat() if viva_assignment else None)
            ),
            "total_marks": round(float(viva_assignment.total_marks or 0), 2) if viva_assignment else 0.0,
            "remarks": viva_assignment.remarks if viva_assignment else None,
            "rubric_rows": viva_rubric_rows,
        },
        "final_result": final_result,
    }

    return report_data, None, None


def build_subject_summary_rows(exam, questions, submissions_by_question):
    grouped_questions: dict[str, list] = defaultdict(list)
    for question in questions:
        grouped_questions[question.subject].append(question)

    rows = []
    for index, subject_name in enumerate(sorted(grouped_questions.keys()), start=1):
        subject_questions = grouped_questions[subject_name]
        correct_answers = 0
        wrong_answers = 0
        skipped_answers = 0
        obtained_marks = 0.0
        total_marks = sum(float(question.marks or 0) for question in subject_questions)

        for question in subject_questions:
            submission = submissions_by_question.get(question.id)
            if not submission:
                skipped_answers += 1
                continue
            if submission.is_correct:
                correct_answers += 1
                obtained_marks += float(question.marks or 0)
            else:
                wrong_answers += 1

        rows.append(
            {
                "sl": index,
                "subject_name": subject_name,
                "total_questions": len(subject_questions),
                "correct_answers": correct_answers,
                "wrong_answers": wrong_answers,
                "skipped_answers": skipped_answers,
                "obtained_marks": round(obtained_marks, 2),
                "total_marks": round(total_marks, 2),
            }
        )

    return rows


def build_student_answer_display(question, submission):
    if not submission:
        return None

    if question.type == "option":
        options = get_question_options(question)
        option_key = resolve_submitted_option_key(question, submission.answer)
        if option_key is None:
            return {"key": None, "text": submission.answer}
        return {"key": option_key, "text": options.get(option_key)}

    return {"key": None, "text": submission.answer}


def build_correct_answer_display(question):
    if question.type == "option":
        return get_correct_option_answers_display(question)
    return [{"key": None, "text": getattr(question, "answer", "")}]


def build_question_reviews(questions, submissions_by_question):
    reviews = []
    for question in questions:
        submission = submissions_by_question.get(question.id)
        if not submission:
            status_label = "SKIPPED"
            is_correct = False
        else:
            status_label = "CORRECT" if submission.is_correct else "WRONG"
            is_correct = bool(submission.is_correct)

        reviews.append(
            {
                "question_id": question.id,
                "subject": question.subject,
                "question_text": question.question_text,
                "question_type": question.type,
                "marks": float(question.marks or 0),
                "options": get_question_options(question),
                "student_answer": build_student_answer_display(question, submission),
                "correct_answers": build_correct_answer_display(question),
                "status": status_label,
                "is_correct": is_correct,
            }
        )
    return reviews


def build_final_result(exam, student, summary, viva_assignment):
    existing_result = AdmissionResult.objects.filter(exam=exam, student=student).select_related(
        "configuration", "department"
    ).first()
    department = get_student_department(student) or resolve_department_for_exam(exam)
    configuration = AdmissionConfiguration.objects.filter(
        department=department,
        semester=exam.semester,
    ).first()

    threshold = None
    if configuration:
        threshold = float(configuration.threshold)
    else:
        legacy_threshold = DepartmentThreshold.objects.filter(
            exam=exam,
            department=department,
        ).first()
        if legacy_threshold:
            threshold = float(legacy_threshold.min_threshold_mark)

    distribution = MarksDistribution.objects.filter(department=department).first() if department else None
    viva_marks = float(viva_assignment.total_marks or 0) if viva_assignment else 0.0
    written_marks = float(summary["obtained_marks"])
    written_viva_total = round(written_marks + viva_marks, 2)

    if existing_result:
        weighted_total = float(existing_result.weighted_total_marks or 0)
        result_status = existing_result.result_status
        ssc_contribution = float(existing_result.ssc_contribution or 0)
        academic_contribution = float(existing_result.academic_contribution or 0)
        written_contribution = float(existing_result.written_contribution or 0)
        viva_contribution = float(existing_result.viva_contribution or 0)
        academic_source = existing_result.academic_source
        academic_score = float(existing_result.academic_score or 0)
        ssc_score = float(existing_result.ssc_score or 0)
    else:
        weighted = calculate_weighted_scores(
            student=student,
            exam=exam,
            department=department,
            mcq_marks=written_marks,
            viva_marks=viva_marks,
        )
        weighted_total = float(weighted["weighted_total_marks"])
        ssc_contribution = float(weighted["ssc_contribution"])
        academic_contribution = float(weighted["academic_contribution"])
        written_contribution = float(weighted["written_contribution"])
        viva_contribution = float(weighted["viva_contribution"])
        academic_source = weighted["academic_source"]
        academic_score = float(weighted["academic_score"])
        ssc_score = float(weighted["ssc_score"])

        if summary["total_questions_attempted"] == 0:
            result_status = "ABSENT"
        elif threshold is not None and weighted_total < threshold:
            result_status = "REJECTED"
        else:
            result_status = "WAITING"

    distribution_percentages = None
    if distribution:
        distribution_percentages = {
            "ssc": distribution.ssc,
            "hsc": distribution.hsc,
            "diploma": distribution.diploma,
            "written": distribution.main_marks,
            "viva": distribution.viva_marks,
        }

    return {
        "written_marks": round(written_marks, 2),
        "viva_marks": round(viva_marks, 2),
        "written_viva_total": written_viva_total,
        "weighted_total": round(weighted_total, 2),
        "threshold": round(threshold, 2) if threshold is not None else None,
        "result_status": result_status,
        "ssc_score": round(ssc_score, 2),
        "academic_score": round(academic_score, 2),
        "academic_source": academic_source,
        "ssc_contribution": round(ssc_contribution, 2),
        "academic_contribution": round(academic_contribution, 2),
        "written_contribution": round(written_contribution, 2),
        "viva_contribution": round(viva_contribution, 2),
        "distribution_percentages": distribution_percentages,
    }


@extend_schema(
    operation_id="get_student_admission_detail_report",
    tags=["Admission Management"],
    summary="Get detailed student admission report data",
    description=(
        "Returns one export-ready report payload for a specific student and exam, "
        "including written answers, correct answers, subject summary, viva details, "
        "and final weighted result calculation."
    ),
    responses={200: StudentAdmissionDetailReportSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_student_admission_detail_report(request, exam_id, student_id):
    report_data, error_payload, error_status = build_student_admission_detail_report_data(exam_id, student_id)
    if error_payload is not None:
        return Response(error_payload, status=error_status)

    serializer = StudentAdmissionDetailReportSerializer(report_data)
    return Response({"success": True, "data": serializer.data})


@extend_schema(
    operation_id="download_student_admission_detail_report_pdf",
    tags=["Admission Management"],
    summary="Download detailed student admission report as PDF",
    description=(
        "Generates a print-ready, text-selectable PDF for a specific student and exam "
        "using the same report payload as the detail-report JSON endpoint."
    ),
    responses={
        200: OpenApiResponse(response=OpenApiTypes.BINARY, description="PDF file"),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
@renderer_classes([PDFRenderer])
def download_student_admission_detail_report_pdf(request, exam_id, student_id):
    pdf_bytes, serialized_report, error_payload, error_status = _build_student_admission_report_pdf_bytes(
        request,
        int(exam_id),
        int(student_id),
    )
    if error_payload is not None:
        return JsonResponse(error_payload, status=error_status)

    filename = build_pdf_filename(serialized_report)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@extend_schema(
    operation_id="download_student_admission_detail_report_pdf_batch_zip",
    tags=["Admission Management"],
    summary="Download multiple student admission reports as one ZIP",
    description=(
        "Accepts a list of exam/student pairs, generates each student's admission report PDF, "
        "and returns them in a single ZIP file."
    ),
    responses={
        200: OpenApiResponse(response=OpenApiTypes.BINARY, description="ZIP file"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
@renderer_classes([ZIPRenderer])
def download_student_admission_reports_pdf_batch_zip(request):
    reports = request.data.get("reports")
    if not isinstance(reports, list) or len(reports) == 0:
        return JsonResponse(
            {
                "success": False,
                "message": "The reports field must be a non-empty list.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    zip_buffer = io.BytesIO()
    added_count = 0
    failures: list[str] = []
    used_filenames: set[str] = set()

    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for row in reports:
            exam_id = row.get("exam_id") if isinstance(row, dict) else None
            student_id = row.get("student_id") if isinstance(row, dict) else None

            try:
                exam_id_int = int(exam_id)
                student_id_int = int(student_id)
            except (TypeError, ValueError):
                failures.append(
                    f"Skipped one item due to invalid exam_id/student_id: exam_id={exam_id}, student_id={student_id}"
                )
                continue

            pdf_bytes, serialized_report, error_payload, _ = _build_student_admission_report_pdf_bytes(
                request,
                exam_id_int,
                student_id_int,
            )

            if error_payload is not None:
                failures.append(
                    f"Failed exam_id={exam_id_int}, student_id={student_id_int}: {error_payload.get('message', 'Unknown error')}"
                )
                continue

            filename = build_pdf_filename(serialized_report)
            safe_filename = _ensure_unique_zip_filename(used_filenames, filename)
            zip_file.writestr(safe_filename, pdf_bytes)
            added_count += 1

        if failures:
            zip_file.writestr("errors.txt", "\n".join(failures))

    if added_count == 0:
        return JsonResponse(
            {
                "success": False,
                "message": "No PDF files were generated.",
                "errors": failures,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_name = f"student-admission-reports-{timestamp}.zip"

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return response
