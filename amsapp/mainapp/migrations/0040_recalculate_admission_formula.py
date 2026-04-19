from django.db import migrations, transaction
from django.db.models import Q, Sum


def clamp(value, minimum=0.0, maximum=None):
    value = float(value or 0.0)
    if maximum is not None:
        value = min(value, maximum)
    return max(value, minimum)


def normalize_score(score, max_score):
    if max_score <= 0:
        return 0.0
    return clamp(score, 0.0, max_score) / max_score


def resolve_department_for_exam(Department, exam):
    return Department.objects.filter(
        Q(department_shortname__iexact=exam.department)
        | Q(department_name__iexact=exam.department)
    ).first()


def get_student_department(Department, student):
    department = Department.objects.filter(
        department_shortname__iexact=student.department_shortname
    ).first()
    if department:
        return department

    return Department.objects.filter(
        department_name__iexact=student.department_shortname
    ).first()


def get_academic_score(student):
    diploma_score = clamp(student.diploma)
    hsc_score = clamp(student.hsc)
    if diploma_score > 0:
        return "DIPLOMA", diploma_score
    if hsc_score > 0:
        return "HSC", hsc_score
    return "NONE", 0.0


def get_academic_max_score(academic_source):
    if academic_source == "DIPLOMA":
        return 4.0
    if academic_source == "HSC":
        return 5.0
    return 0.0


def get_written_total_marks(ExamQuestion, exam):
    total_marks = ExamQuestion.objects.filter(exam=exam).aggregate(
        total=Sum("marks")
    )["total"] or 0
    if total_marks > 0:
        return float(total_marks)
    return float(exam.total_marks or 0)


def get_viva_total_marks(VivaAssignment, student, exam):
    viva_assignment = (
        VivaAssignment.objects.filter(student=student, exam=exam)
        .order_by("-created_at")
        .first()
    )
    if not viva_assignment:
        return 0.0

    rubric_snapshot = viva_assignment.rubric_snapshot or []
    return round(
        sum(float(rubric.get("max_marks") or 0) for rubric in rubric_snapshot),
        2,
    )


def determine_result_status(attended_exam, is_above_threshold, existing_status):
    if not attended_exam:
        return "ABSENT"
    if not is_above_threshold:
        return "REJECTED"
    if existing_status == "SELECTED":
        return "SELECTED"
    return "WAITING"


def recalculate_admission_formula(apps, schema_editor):
    AdmissionConfiguration = apps.get_model("mainapp", "AdmissionConfiguration")
    AdmissionResult = apps.get_model("mainapp", "AdmissionResult")
    Department = apps.get_model("mainapp", "Department")
    DepartmentThreshold = apps.get_model("mainapp", "DepartmentThreshold")
    ExamQuestion = apps.get_model("mainapp", "ExamQuestion")
    MarksDistribution = apps.get_model("mainapp", "MarksDistribution")
    VivaAssignment = apps.get_model("mainapp", "VivaAssignment")

    with transaction.atomic():
        for result in AdmissionResult.objects.select_related(
            "student", "exam", "department", "configuration"
        ):
            exam = result.exam
            student = result.student
            department = result.department or get_student_department(Department, student) or resolve_department_for_exam(
                Department,
                exam,
            )
            distribution = (
                MarksDistribution.objects.filter(department=department).first()
                if department
                else None
            )

            academic_source, academic_score = get_academic_score(student)
            ssc_score = clamp(student.ssc)
            written_total_marks = get_written_total_marks(ExamQuestion, exam)
            viva_total_marks = get_viva_total_marks(VivaAssignment, student, exam)

            if distribution:
                academic_weight = (
                    distribution.diploma
                    if academic_source == "DIPLOMA"
                    else distribution.hsc
                )
                ssc_contribution = normalize_score(ssc_score, 5.0) * distribution.ssc
                academic_contribution = normalize_score(
                    academic_score,
                    get_academic_max_score(academic_source),
                ) * academic_weight
                written_contribution = normalize_score(
                    result.mcq_marks,
                    written_total_marks,
                ) * distribution.main_marks
                viva_contribution = normalize_score(
                    result.viva_marks,
                    viva_total_marks,
                ) * distribution.viva_marks
                weighted_total_marks = (
                    ssc_contribution
                    + academic_contribution
                    + written_contribution
                    + viva_contribution
                )
            else:
                ssc_contribution = 0.0
                academic_contribution = 0.0
                written_contribution = 0.0
                viva_contribution = 0.0
                weighted_total_marks = clamp(result.mcq_marks + result.viva_marks)

            configuration = result.configuration
            if not configuration and department:
                configuration = AdmissionConfiguration.objects.filter(
                    department=department,
                    semester=exam.semester,
                ).first()

            threshold = None
            if configuration:
                threshold = float(configuration.threshold or 0)
            elif result.threshold_applied is not None:
                threshold = float(result.threshold_applied)
            elif department:
                legacy_threshold = DepartmentThreshold.objects.filter(
                    exam=exam,
                    department=department,
                ).first()
                if legacy_threshold:
                    threshold = float(legacy_threshold.min_threshold_mark or 0)

            attended_exam = bool(result.attended_exam)
            if threshold is None:
                is_selected = bool(result.is_selected)
                result_status = result.result_status
            else:
                is_selected = attended_exam and (weighted_total_marks >= threshold)
                result_status = determine_result_status(
                    attended_exam=attended_exam,
                    is_above_threshold=is_selected,
                    existing_status=result.result_status,
                )

            update_fields = [
                "ssc_score",
                "academic_score",
                "academic_source",
                "ssc_contribution",
                "academic_contribution",
                "written_contribution",
                "viva_contribution",
                "weighted_total_marks",
                "total_marks",
                "written_viva_total",
                "is_selected",
                "result_status",
                "updated_at",
            ]

            result.ssc_score = round(ssc_score, 2)
            result.academic_score = round(academic_score, 2)
            result.academic_source = academic_source
            result.ssc_contribution = round(ssc_contribution, 2)
            result.academic_contribution = round(academic_contribution, 2)
            result.written_contribution = round(written_contribution, 2)
            result.viva_contribution = round(viva_contribution, 2)
            result.weighted_total_marks = round(weighted_total_marks, 2)
            result.total_marks = round(float(result.mcq_marks or 0) + float(result.viva_marks or 0), 2)
            result.written_viva_total = result.total_marks
            result.is_selected = is_selected
            result.result_status = result_status

            if threshold is not None:
                result.threshold_applied = round(threshold, 2)
                update_fields.append("threshold_applied")
            if department and result.department_id != department.id:
                result.department = department
                update_fields.append("department")
            if configuration and result.configuration_id != configuration.id:
                result.configuration = configuration
                update_fields.append("configuration")

            result.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0039_vivaassignment_report_fields"),
    ]

    operations = [
        migrations.RunPython(
            recalculate_admission_formula,
            migrations.RunPython.noop,
        ),
    ]
