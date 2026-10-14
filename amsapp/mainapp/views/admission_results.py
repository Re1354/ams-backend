from datetime import datetime, time, timedelta
import logging

logger = logging.getLogger(__name__)

from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

from ..authentication import CustomJWTAuthentication
from ..services.access_control import get_user_access_scope
from ..models import AdmissionConfiguration, AdmissionResult, Department, DepartmentThreshold, Exam
from ..models import StudentAssignTeacherExam, Students, Submission
from ..serializers.admission_result import (
    AdmissionConfigurationSerializer,
    AdmissionConfigurationUpsertSerializer,
    AdmissionResultSerializer,
    BulkAdmissionStatusUpdateSerializer,
    CalculateAdmissionResultsSerializer,
    CalculateResultsResponseSerializer,
)
from ..services.admission_calculator import (
    THRESHOLD_EPSILON,
    apply_semester_result_statuses,
    calculate_admission_results,
    calculate_semester_admission_results,
    get_threshold_mapping_for_semester,
    get_or_create_admission_configuration,
    get_candidate_students_for_exam,
    has_semester_submission,
    is_configuration_complete,
    recalculate_single_student_result,
    resolve_department_for_exam,
    summarize_status_counts,
    build_candidate_tiebreak_key,
    get_priority_subject_names_for_department,
)
from ..utils import normalize_semester_filter, semester_sort_key


class AdmissionResultsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def get_single_configuration(filters):
    # order_by() clears the model's default ordering, whose columns would
    # otherwise be added to the DISTINCT and split one configuration into
    # multiple "distinct" rows.
    config_ids = list(
        filters.exclude(configuration__isnull=True)
        .order_by()
        .values_list("configuration_id", flat=True)
        .distinct()[:2]
    )
    if len(config_ids) == 1:
        return AdmissionConfiguration.objects.filter(id=config_ids[0]).first()
    return None


def resolve_reverted_status(result):
    if not result.attended_exam:
        # A student is ABSENT only if they sat no exam this semester. If they
        # submitted a different exam, this is a stray row (the recalc that runs
        # right after a revert removes it); keep it out of the Absent tab.
        department = resolve_department_for_exam(result.exam)
        if department and has_semester_submission(
            result.student, department, result.exam.semester
        ):
            return "REJECTED"
        return "ABSENT"
    if is_threshold_qualified(result):
        return "WAITING"
    return "REJECTED"


def get_effective_threshold(result):
    threshold_value = result.threshold_applied
    if threshold_value is None and result.configuration:
        threshold_value = result.configuration.threshold
    return threshold_value


def is_threshold_qualified(result):
    threshold_value = get_effective_threshold(result)
    return (
        result.attended_exam
        and threshold_value is not None
        and result.weighted_total_marks >= float(threshold_value) - THRESHOLD_EPSILON
    )


def filter_visible_results_by_exam_schedule(results):
    """
    Hide unattempted assigned candidates until their assigned schedule has ended.
    Existing premature ABSENT rows can remain stored, but they should not appear
    on the result board before the exam window is over.
    """
    now = timezone.now()
    ended_assignment = StudentAssignTeacherExam.objects.filter(
        student_id=OuterRef("student_id"),
        exam_id=OuterRef("exam_id"),
        schedule__end_time__lte=now,
    )
    future_assignment = StudentAssignTeacherExam.objects.filter(
        student_id=OuterRef("student_id"),
        exam_id=OuterRef("exam_id"),
        schedule__end_time__gt=now,
    )

    return (
        results.annotate(
            has_ended_assignment=Exists(ended_assignment),
            has_future_assignment=Exists(future_assignment),
        )
        .exclude(
            attended_exam=False,
            has_ended_assignment=False,
            has_future_assignment=True,
        )
    )


def resolve_configuration_from_payload(validated_data):
    exam = None
    department = None
    semester = validated_data.get("semester")

    exam_id = validated_data.get("exam_id")
    if exam_id:
        exam = Exam.objects.filter(id=exam_id).first()
        if not exam:
            return None, None, "Exam not found"
        department = resolve_department_for_exam(exam)
        semester = exam.semester
    else:
        department = Department.objects.filter(id=validated_data["department_id"]).first()

    if not department:
        return None, None, "Department could not be resolved"

    configuration = None
    if exam:
        configuration = get_or_create_admission_configuration(exam, department)
    else:
        configuration, _ = AdmissionConfiguration.objects.get_or_create(
            department=department,
            semester=semester,
        )

    updates = []
    if exam and configuration.exam_id != exam.id:
        configuration.exam = exam
        updates.append("exam")
    if "seat_limit" in validated_data:
        configuration.seat_limit = validated_data["seat_limit"]
        updates.append("seat_limit")
    if "waiting_student_limit" in validated_data:
        configuration.waiting_student_limit = validated_data["waiting_student_limit"]
        updates.append("waiting_student_limit")
    if "threshold" in validated_data:
        configuration.threshold = validated_data["threshold"]
        updates.append("threshold")
    if "notes" in validated_data:
        configuration.notes = validated_data["notes"]
        updates.append("notes")

    if updates:
        configuration.save(update_fields=updates + ["updated_at"])

    if any(field in validated_data for field in ("seat_limit", "threshold", "waiting_student_limit")):
        DepartmentThreshold.objects.update_or_create(
            semester=configuration.semester,
            department=configuration.department,
            defaults={
                "min_threshold_mark": configuration.threshold,
                "seat_limit": configuration.seat_limit,
                "waiting_student_limit": configuration.waiting_student_limit,
                "exam": exam or configuration.exam,
            },
        )

    return configuration, exam, None


def get_exam_queryset_for_department_semester(department=None, semester=None):
    exams = Exam.objects.all()
    if semester:
        exams = exams.filter(semester__iexact=normalize_semester_filter(semester))

    if not department:
        return exams

    department_name = department.department_name.strip()
    department_shortname = department.department_shortname.strip()
    return exams.filter(
        Q(department__iexact=department_name) | Q(department__iexact=department_shortname)
    )


def ensure_semester_admission_results(department=None, semester=None):
    """
    Make sure admission rows exist for exams in the selected department + semester.

    The examinee board is semester-driven in the UI, so this keeps the existing
    AdmissionResult workflow but backfills missing rows from real exam
    participation data when a newer semester has not been calculated yet.
    """
    if not semester:
        return

    if not department:
        norm_sem = normalize_semester_filter(semester)
        configured_depts = Department.objects.filter(
            admission_thresholds__semester__iexact=norm_sem,
            admission_thresholds__min_threshold_mark__isnull=False,
            admission_thresholds__seat_limit__gt=0,
        ).distinct()
        for dept in configured_depts:
            ensure_semester_admission_results(department=dept, semester=semester)
        return

    threshold_mapping = get_threshold_mapping_for_semester(department, semester)
    if not is_configuration_complete(threshold_mapping):
        return

    semester_exams = list(
        get_exam_queryset_for_department_semester(department=department, semester=semester)
    )
    if not semester_exams:
        return

    # Recalculate when any assigned student whose exam window has already ended
    # is still missing a result row — i.e. an absentee who never submitted. The
    # old guard skipped as soon as ANY row existed, so a single submitter during
    # the exam permanently blocked absentees from ever being generated once the
    # window closed. This check is self-limiting: after the backfill runs the
    # rows exist, so it won't re-trigger. Windows still open (end_time > now) are
    # excluded, so absentees are never generated prematurely.
    now = timezone.now()
    missing_absentees = (
        StudentAssignTeacherExam.objects.filter(
            exam__in=semester_exams,
            schedule__end_time__lte=now,
        )
        .exclude(
            Exists(
                AdmissionResult.objects.filter(
                    exam_id=OuterRef("exam_id"),
                    student_id=OuterRef("student_id"),
                )
            )
        )
        .exists()
    )
    if not missing_absentees:
        return

    calculate_semester_admission_results(department=department, semester=semester)


@extend_schema(
    operation_id="upsert_admission_configuration",
    tags=["Admission Management"],
    summary="Create or update admission configuration",
    description=(
        "Stores seat limit and threshold once for a department + semester and "
        "reuses it later during result calculations."
    ),
    request=AdmissionConfigurationUpsertSerializer,
    responses={200: AdmissionConfigurationSerializer, 201: AdmissionConfigurationSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def admission_configurations(request):
    scope = get_user_access_scope(request.user)

    if request.method == "GET":
        queryset = AdmissionConfiguration.objects.select_related("department", "exam").all()
        
        if not scope['is_global']:
            if not scope['department_ids']:
                queryset = queryset.none()
            else:
                queryset = queryset.filter(department_id__in=scope['department_ids'])
        semester = request.query_params.get("semester")
        department_id = request.query_params.get("department_id")
        exam_id = request.query_params.get("exam_id")

        if semester:
            queryset = queryset.filter(semester__iexact=normalize_semester_filter(semester))
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)

        serializer = AdmissionConfigurationSerializer(queryset.order_by("semester"), many=True)
        return Response(
            {
                "success": True,
                "count": queryset.count(),
                "configurations": serializer.data,
            }
        )

    serializer = AdmissionConfigurationUpsertSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Invalid request data", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not scope['is_global']:
        target_department_id = None
        exam_id = serializer.validated_data.get("exam_id")
        if exam_id:
            exam = Exam.objects.filter(id=exam_id).first()
            if exam:
                dept = resolve_department_for_exam(exam)
                if dept:
                    target_department_id = dept.id
        else:
            target_department_id = serializer.validated_data.get("department_id")
            
        if not target_department_id or target_department_id not in scope['department_ids']:
            return Response(
                {"success": False, "message": "You do not have access to this department."},
                status=status.HTTP_403_FORBIDDEN,
            )

    configuration, _, error = resolve_configuration_from_payload(serializer.validated_data)
    if error:
        return Response(
            {"success": False, "message": error},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if any(field in serializer.validated_data for field in ("seat_limit", "threshold", "waiting_student_limit")):
        calculate_semester_admission_results(
            department=configuration.department,
            semester=configuration.semester,
        )

    response_serializer = AdmissionConfigurationSerializer(configuration)
    return Response(
        {
            "success": True,
            "message": "Admission configuration saved successfully",
            "data": response_serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    operation_id="get_admission_configuration_by_id",
    tags=["Admission Management"],
    summary="Get or update one admission configuration",
    request=AdmissionConfigurationUpsertSerializer,
    responses={200: AdmissionConfigurationSerializer},
)
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def admission_configuration_detail(request, config_id):
    try:
        configuration = AdmissionConfiguration.objects.select_related("department", "exam").get(
            id=config_id
        )
    except AdmissionConfiguration.DoesNotExist:
        return Response(
            {"success": False, "message": "Admission configuration not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(
            {
                "success": True,
                "data": AdmissionConfigurationSerializer(configuration).data,
            }
        )

    serializer = AdmissionConfigurationUpsertSerializer(data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Invalid request data", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    for field in ("seat_limit", "waiting_student_limit", "threshold", "notes"):
        if field in serializer.validated_data:
            setattr(configuration, field, serializer.validated_data[field])
    configuration.save()

    if any(field in serializer.validated_data for field in ("seat_limit", "threshold", "waiting_student_limit")):
        DepartmentThreshold.objects.update_or_create(
            semester=configuration.semester,
            department=configuration.department,
            defaults={
                "min_threshold_mark": configuration.threshold,
                "seat_limit": configuration.seat_limit,
                "waiting_student_limit": configuration.waiting_student_limit,
                "exam": configuration.exam,
            },
        )
        calculate_semester_admission_results(
            department=configuration.department,
            semester=configuration.semester,
        )

    return Response(
        {
            "success": True,
            "message": "Admission configuration updated successfully",
            "data": AdmissionConfigurationSerializer(configuration).data,
        }
    )


@extend_schema(
    operation_id="get_admission_semesters",
    tags=["Admission Management"],
    summary="Get semester options for admission pages",
    responses={200: OpenApiResponse(description="Semester list retrieved successfully")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def admission_semester_options(request):
    scope = get_user_access_scope(request.user)
    department_id = request.query_params.get("department_id")
    faculty_id = request.query_params.get("faculty_id")

    allowed_dept_ids = None
    if department_id:
        if not scope["is_global"] and int(department_id) not in scope["department_ids"]:
            return Response({"success": True, "semesters": []})
        allowed_dept_ids = [int(department_id)]
    elif faculty_id:
        fac_depts = list(Department.objects.filter(faculty_id=faculty_id).values_list("id", flat=True))
        if not scope["is_global"]:
            allowed_dept_ids = [d for d in fac_depts if d in scope["department_ids"]]
        else:
            allowed_dept_ids = fac_depts
    elif not scope["is_global"]:
        allowed_dept_ids = scope["department_ids"]

    semesters_set = set()

    # 1. From Exam
    exam_qs = Exam.objects.all()
    if allowed_dept_ids is not None:
        valid_departments = Department.objects.filter(id__in=allowed_dept_ids)
        q_exam = Q()
        for vd in valid_departments:
            q_exam |= Q(department__iexact=vd.department_name) | Q(department__iexact=vd.department_shortname)
        if faculty_id:
            q_exam |= Q(faculty_ref_id=faculty_id)
        exam_qs = exam_qs.filter(q_exam)
    for s in exam_qs.exclude(semester__isnull=True).exclude(semester="").values_list("semester", flat=True).distinct():
        if s and s.strip():
            semesters_set.add(s.strip())

    # 2. From DepartmentThreshold
    dt_qs = DepartmentThreshold.objects.all()
    if allowed_dept_ids is not None:
        dt_qs = dt_qs.filter(department_id__in=allowed_dept_ids)
    for s in dt_qs.exclude(semester__isnull=True).exclude(semester="").values_list("semester", flat=True).distinct():
        if s and s.strip():
            semesters_set.add(s.strip())

    # 3. From AdmissionConfiguration
    ac_qs = AdmissionConfiguration.objects.all()
    if allowed_dept_ids is not None:
        ac_qs = ac_qs.filter(department_id__in=allowed_dept_ids)
    for s in ac_qs.exclude(semester__isnull=True).exclude(semester="").values_list("semester", flat=True).distinct():
        if s and s.strip():
            semesters_set.add(s.strip())

    # 4. From Students registration_semester
    stu_qs = Students.objects.all()
    if allowed_dept_ids is not None:
        valid_departments = Department.objects.filter(id__in=allowed_dept_ids)
        q_stu = Q()
        for vd in valid_departments:
            q_stu |= Q(department_shortname__iexact=vd.department_shortname)
            q_stu |= Q(department_choices__contains=[{"department_id": vd.id}])
        stu_qs = stu_qs.filter(q_stu)
    for s in stu_qs.exclude(registration_semester__isnull=True).exclude(registration_semester="").values_list("registration_semester", flat=True).distinct():
        if s and s.strip():
            semesters_set.add(s.strip())

    semesters = sorted(semesters_set, key=semester_sort_key)
    return Response({"success": True, "semesters": semesters})


@extend_schema(
    operation_id="calculate_admission_results",
    tags=["Admission Management"],
    summary="Calculate admission results for an exam",
    description=(
        "Calculates semester-aware admission results using assigned students, "
        "weighted totals, and the department + semester configuration."
    ),
    request=CalculateAdmissionResultsSerializer,
    responses={200: CalculateResultsResponseSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def calculate_results(request):
    serializer = CalculateAdmissionResultsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Invalid request data", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    exam_id = serializer.validated_data["exam_id"]
    
    scope = get_user_access_scope(request.user)
    if not scope['is_global']:
        exam = Exam.objects.filter(id=exam_id).first()
        if not exam:
            return Response({"success": False, "message": "Exam not found"}, status=status.HTTP_404_NOT_FOUND)
        dept = resolve_department_for_exam(exam)
        if not dept or dept.id not in scope['department_ids']:
            return Response(
                {"success": False, "message": "You do not have access to this department."},
                status=status.HTTP_403_FORBIDDEN,
            )

    result = calculate_admission_results(exam_id)

    if not result["success"]:
        return Response(
            {
                "success": False,
                "message": "Failed to calculate results",
                "errors": result.get("errors", []),
                "configuration_missing": result.get("configuration_missing", False),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    response_data = {
        "success": True,
        "message": f"Results calculated successfully. Processed {result['processed_count']} students.",
        "processed_count": result["processed_count"],
        "selected_count": result["selected_count"],
        "not_selected_count": result["not_selected_count"],
        "status_counts": result.get("status_counts", {}),
        "configuration_id": result.get("configuration_id"),
        "configuration_missing": result.get("configuration_missing", False),
        "exam_id": exam_id,
    }
    if result.get("errors"):
        response_data["warnings"] = result["errors"]

    return Response(response_data)


@extend_schema(
    operation_id="get_admission_results",
    tags=["Admission Management"],
    summary="Get admission results with examinee board filters",
    parameters=[
        OpenApiParameter(name="exam_id", required=False, type=int),
        OpenApiParameter(name="configuration_id", required=False, type=int),
        OpenApiParameter(name="department_id", required=False, type=int),
        OpenApiParameter(name="faculty_id", required=False, type=int),
        OpenApiParameter(name="student_id", required=False, type=int),
        OpenApiParameter(name="semester", required=False, type=str),
        OpenApiParameter(name="search", required=False, type=str),
        OpenApiParameter(name="is_selected", required=False, type=bool),
        OpenApiParameter(name="attended_exam", required=False, type=bool),
        OpenApiParameter(name="status", required=False, type=str),
        OpenApiParameter(name="result_status", required=False, type=str),
        OpenApiParameter(name="exclude_result_status", required=False, type=str),
        OpenApiParameter(name="minimum_score", required=False, type=float),
        OpenApiParameter(name="sort_by", required=False, type=str),
        OpenApiParameter(name="order", required=False, type=str),
        OpenApiParameter(name="exam_taken_date", required=False, type=str),
        OpenApiParameter(name="page", required=False, type=int),
        OpenApiParameter(name="page_size", required=False, type=int),
    ],
    responses={200: AdmissionResultSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_admission_results(request):
    scope = get_user_access_scope(request.user)

    exam_id = request.query_params.get("exam_id")
    configuration_id = request.query_params.get("configuration_id")
    department_id = request.query_params.get("department_id")
    faculty_id = request.query_params.get("faculty_id")
    student_id = request.query_params.get("student_id")
    semester = request.query_params.get("semester")
    search = request.query_params.get("search")
    is_selected = request.query_params.get("is_selected")
    attended_exam = request.query_params.get("attended_exam")
    publication_status = request.query_params.get("status")
    result_status = request.query_params.get("result_status")
    exclude_result_status = request.query_params.get("exclude_result_status")
    minimum_score = request.query_params.get("minimum_score")
    sort_by = request.query_params.get("sort_by", "score")
    order = request.query_params.get("order", "desc")
    configuration_missing = False
    unconfigured_exam_semesters = []

    if semester:
        norm_sem = normalize_semester_filter(semester)
        resolved_department = (
            Department.objects.filter(id=department_id).first() if department_id else None
        )
        try:
            ensure_semester_admission_results(
                department=resolved_department,
                semester=semester,
            )
        except Exception as exc:
            logger.warning("ensure_semester_admission_results failed during results load: %s", exc)
        if resolved_department:
            threshold_mapping = get_threshold_mapping_for_semester(resolved_department, semester)
            configuration_missing = not is_configuration_complete(threshold_mapping)
            exam_semesters = (
                get_exam_queryset_for_department_semester(department=resolved_department)
                .values_list("semester", flat=True)
                .distinct()
            )
            unconfigured_exam_semesters = sorted(
                {
                    exam_semester
                    for exam_semester in exam_semesters
                    if not is_configuration_complete(
                        get_threshold_mapping_for_semester(resolved_department, exam_semester)
                    )
                },
                key=semester_sort_key,
            )

    results = AdmissionResult.objects.select_related(
        "exam",
        "student",
        "department",
        "configuration",
        "configuration__department",
        "configuration__exam",
    ).all()

    if not scope["is_global"]:
        if not scope["department_ids"]:
            results = results.none()
        else:
            scope_depts = scope["department_ids"]
            scope_q = Q(department_id__in=scope_depts)
            for d_id in scope_depts:
                scope_q |= Q(student__department_choices__contains=[{"department_id": d_id}])
            scope_shortnames = list(
                Department.objects.filter(id__in=scope_depts).values_list("department_shortname", flat=True)
            )
            scope_q |= (
                (Q(student__department_choices=[]) | Q(student__department_choices__isnull=True))
                & Q(student__department_shortname__in=scope_shortnames)
            )
            results = results.filter(scope_q).distinct()

    if exam_id:
        results = results.filter(exam_id=exam_id)
    if configuration_id:
        results = results.filter(configuration_id=configuration_id)
    if department_id:
        target_dept = Department.objects.filter(id=department_id).first()
        if target_dept:
            dept_q = (
                Q(department_id=target_dept.id)
                | Q(student__department_choices__contains=[{"department_id": target_dept.id}])
            )
            if target_dept.department_shortname:
                dept_q |= (
                    (Q(student__department_choices=[]) | Q(student__department_choices__isnull=True))
                    & Q(student__department_shortname__iexact=target_dept.department_shortname)
                )
            results = results.filter(dept_q).distinct()
        else:
            results = results.filter(department_id=department_id)
    if faculty_id:
        fac_dept_ids = list(Department.objects.filter(faculty_id=faculty_id).values_list("id", flat=True))
        fac_dept_shorts = list(
            Department.objects.filter(faculty_id=faculty_id).values_list("department_shortname", flat=True)
        )
        fac_q = Q(department_id__in=fac_dept_ids)
        for d_id in fac_dept_ids:
            fac_q |= Q(student__department_choices__contains=[{"department_id": d_id}])
        fac_q |= (
            (Q(student__department_choices=[]) | Q(student__department_choices__isnull=True))
            & Q(student__department_shortname__in=fac_dept_shorts)
        )
        fac_q |= Q(exam__faculty_ref_id=faculty_id)
        results = results.filter(fac_q).distinct()
    if student_id:
        results = results.filter(student_id=student_id)
    if semester:
        norm_sem = normalize_semester_filter(semester)
        results = results.filter(
            Q(configuration__semester__iexact=semester)
            | Q(configuration__semester__iexact=norm_sem)
            | Q(exam__semester__iexact=semester)
            | Q(exam__semester__iexact=norm_sem)
            | (
                Q(configuration__isnull=True)
                & Q(exam__isnull=True)
                & (
                    Q(student__registration_semester__iexact=semester)
                    | Q(student__registration_semester__iexact=norm_sem)
                )
            )
        )

    if is_selected is not None:
        results = results.filter(is_selected=is_selected.lower() in {"true", "1", "yes"})
    if attended_exam is not None:
        results = results.filter(attended_exam=attended_exam.lower() in {"true", "1", "yes"})
    if publication_status:
        results = results.filter(status__iexact=publication_status)

    results = filter_visible_results_by_exam_schedule(results)
    # Board identity and the top summary cards are independent of the search/date
    # filters, so resolve them from the whole visible cohort *before* those are
    # applied: `total_summary` feeds the cards (always the semester totals) while
    # `summary` below feeds the tab counts (which track the active filters).
    configuration = get_single_configuration(results)
    total_summary = summarize_status_counts(results)

    if search:
        results = results.filter(
            Q(student__username__icontains=search)
            | Q(student__full_name__icontains=search)
            | Q(student__f_id__icontains=search)
        )

    # Exam-taken datetime = latest submission by this student for this exam.
    # Absent students have no submission -> null (sorted last, blank in UI).
    # Annotate + apply the date filter *before* summarizing, so the per-status
    # tab counts track the active date filter instead of the whole-cohort totals.
    latest_submission = (
        Submission.objects.filter(student=OuterRef("student"), exam=OuterRef("exam"))
        .order_by("-submitted_at")
        .values("submitted_at")[:1]
    )
    results = results.annotate(exam_taken_at=Subquery(latest_submission))

    exam_taken_date = request.query_params.get("exam_taken_date")
    start_date = request.query_params.get("start_date") or request.query_params.get("exam_taken_date_from")
    end_date = request.query_params.get("end_date") or request.query_params.get("exam_taken_date_to")

    local_tz = timezone.get_current_timezone()
    if start_date or end_date:
        if start_date:
            parsed_start = parse_date(start_date)
            if parsed_start:
                day_start = datetime.combine(parsed_start, time.min, tzinfo=local_tz)
                results = results.filter(exam_taken_at__gte=day_start)
        if end_date:
            parsed_end = parse_date(end_date)
            if parsed_end:
                day_end = datetime.combine(parsed_end + timedelta(days=1), time.min, tzinfo=local_tz)
                results = results.filter(exam_taken_at__lt=day_end)
    elif exam_taken_date:
        parsed_date = parse_date(exam_taken_date)
        if parsed_date:
            day_start = datetime.combine(parsed_date, time.min, tzinfo=local_tz)
            results = results.filter(
                exam_taken_at__gte=day_start,
                exam_taken_at__lt=day_start + timedelta(days=1),
            )

    summary_queryset = results
    summary = summarize_status_counts(summary_queryset)

    if result_status:
        # ACCEPTED is virtual: admitted rows keep result_status=SELECTED, so the
        # Selected tab must exclude them and the Accepted tab filters the flag.
        normalized_status = result_status.upper()
        if normalized_status == "ACCEPTED":
            results = results.filter(is_admitted=True)
        elif normalized_status == "SELECTED":
            results = results.filter(result_status="SELECTED", is_admitted=False)
        else:
            results = results.filter(result_status__iexact=result_status)
    if exclude_result_status:
        results = results.exclude(result_status__iexact=exclude_result_status)
    if minimum_score not in (None, ""):
        try:
            results = results.filter(weighted_total_marks__gte=float(minimum_score))
        except (TypeError, ValueError):
            pass

    order_prefix = "" if order == "asc" else "-"
    sort_mapping = {
        "score": f"{order_prefix}weighted_total_marks",
        "form_id": f"{order_prefix}student__f_id",
        "serial": f"{order_prefix}id",
    }
    if sort_by in ("exams_taken", "exam_count", "exams"):
        results = results.annotate(
            exams_taken_count=Count("student__submissions__exam", distinct=True)
        )
        exam_count_order = (
            F("exams_taken_count").asc() if order == "asc" else F("exams_taken_count").desc()
        )
        results = results.order_by(exam_count_order, "-weighted_total_marks", "-created_at")
    elif sort_by == "date":
        date_order = (
            F("exam_taken_at").asc(nulls_last=True)
            if order == "asc"
            else F("exam_taken_at").desc(nulls_last=True)
        )
        results = results.order_by(date_order, "-created_at")
    elif sort_by in ("score", None, ""):
        results = results.order_by(
            f"{order_prefix}weighted_total_marks",
            "-written_viva_total" if order != "asc" else "written_viva_total",
            "-mcq_marks" if order != "asc" else "mcq_marks",
            "-created_at",
        )
        results_list = list(results)
        dept_priorities_cache = {}

        def get_cached_priority_subjects(item):
            dept = item.department or getattr(item.configuration, "department", None)
            dept_id = dept.id if dept else None
            if dept_id not in dept_priorities_cache:
                dept_priorities_cache[dept_id] = (
                    get_priority_subject_names_for_department(dept) if dept else []
                )
            return dept_priorities_cache[dept_id]

        try:
            results_list.sort(
                key=lambda item: build_candidate_tiebreak_key(
                    item, get_cached_priority_subjects(item)
                ),
                reverse=(order == "asc"),
            )
            results = results_list
        except Exception as sort_exc:
            logger.warning("Error in candidate tie-break sorting: %s", sort_exc)
            results = results.order_by(
                f"{order_prefix}weighted_total_marks",
                "-written_viva_total" if order != "asc" else "written_viva_total",
                "-mcq_marks" if order != "asc" else "mcq_marks",
                "-created_at",
            )
    else:
        results = results.order_by(sort_mapping.get(sort_by, "-weighted_total_marks"), "-created_at")

    paginator = AdmissionResultsPagination()
    page = paginator.paginate_queryset(results, request)
    serializer = AdmissionResultSerializer(page if page is not None else results, many=True)

    if page is not None:
        response = paginator.get_paginated_response(serializer.data)
        response.data["success"] = True
        response.data["summary"] = summary
        response.data["total_summary"] = total_summary
        response.data["configuration"] = (
            AdmissionConfigurationSerializer(configuration).data if configuration else None
        )
        response.data["configuration_missing"] = configuration_missing
        response.data["unconfigured_exam_semesters"] = unconfigured_exam_semesters
        response.data["filters_applied"] = {
            "exam_id": exam_id,
            "configuration_id": configuration_id,
            "department_id": department_id,
            "student_id": student_id,
            "semester": semester,
            "search": search,
            "is_selected": is_selected,
            "attended_exam": attended_exam,
            "status": publication_status,
            "result_status": result_status,
            "exclude_result_status": exclude_result_status,
            "minimum_score": minimum_score,
            "sort_by": sort_by,
            "order": order,
            "exam_taken_date": exam_taken_date,
        }
        return response

    return Response(
        {
            "success": True,
            "count": results.count(),
            "summary": summary,
            "total_summary": total_summary,
            "configuration": (
                AdmissionConfigurationSerializer(configuration).data if configuration else None
            ),
            "configuration_missing": configuration_missing,
            "unconfigured_exam_semesters": unconfigured_exam_semesters,
            "results": serializer.data,
        }
    )


@extend_schema(
    operation_id="bulk_update_admission_result_status",
    tags=["Admission Management"],
    summary="Bulk update candidate result status",
    description=(
        "Used by the examinee board to accept candidates or move them back to "
        "waiting/rejected without duplicating result rows."
    ),
    request=BulkAdmissionStatusUpdateSerializer,
    responses={200: OpenApiResponse(description="Statuses updated successfully")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def bulk_update_admission_result_status(request):
    serializer = BulkAdmissionStatusUpdateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Invalid request data", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    validated = serializer.validated_data
    student_ids = validated["student_ids"]
    action = validated.get("action", "SET_STATUS")
    target_status = validated.get("result_status")

    queryset = AdmissionResult.objects.select_related("configuration", "student").filter(student_id__in=student_ids)
    if validated.get("configuration_id"):
        queryset = queryset.filter(configuration_id=validated["configuration_id"])
    if validated.get("exam_id"):
        queryset = queryset.filter(exam_id=validated["exam_id"])

    results = list(queryset)
    if not results:
        return Response(
            {"success": False, "message": "No admission results matched the requested students."},
            status=status.HTTP_404_NOT_FOUND,
        )

    configuration = results[0].configuration
    if not configuration:
        return Response(
            {"success": False, "message": "Selected results are missing an admission configuration."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if any(result.configuration_id != configuration.id for result in results):
        return Response(
            {
                "success": False,
                "message": "All selected candidates must belong to the same admission configuration.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    threshold_mapping = get_threshold_mapping_for_semester(
        configuration.department,
        configuration.semester,
    )
    if not is_configuration_complete(threshold_mapping):
        return Response(
            {
                "success": False,
                "message": "Threshold or seat limit is not set for this semester.",
                "configuration_missing": True,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    had_override = any(result.is_override_accepted for result in results)
    recalc_required = False

    if action == "SET_ADMITTED":
        not_selected = [
            result.student.username
            for result in results
            if result.result_status != "SELECTED"
        ]
        if not_selected:
            return Response(
                {
                    "success": False,
                    "message": "Only selected candidates can be accepted for admission.",
                    "invalid_candidates": not_selected,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rows are already SELECTED and hold their seats; no recalc needed.
        queryset.update(is_admitted=True)
        message = f"Accepted {len(results)} candidates for admission."
    elif action == "SET_STATUS":
        if target_status == "SELECTED":
            recalc_required = True

        if target_status == "WAITING":
            invalid_candidates = [
                result.student.username
                for result in results
                if not is_threshold_qualified(result)
            ]
            if invalid_candidates:
                return Response(
                    {
                        "success": False,
                        "message": "Only attended candidates above threshold can be moved to waiting.",
                        "invalid_candidates": invalid_candidates,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            if target_status == "SELECTED":
                queryset.update(
                    result_status=target_status,
                    is_override_accepted=True,
                    is_admitted=True,
                )
            else:
                queryset.update(
                    result_status=target_status,
                    is_override_accepted=False,
                    is_admitted=False,
                    is_selected=False,
                )
                if had_override:
                    recalc_required = True

        message = f"Updated {len(results)} candidates to {target_status}."
    else:
        with transaction.atomic():
            for result in results:
                result.result_status = resolve_reverted_status(result)
                result.is_override_accepted = False
                result.is_admitted = False
                result.is_selected = False
                result.save(
                    update_fields=[
                        "result_status",
                        "is_override_accepted",
                        "is_admitted",
                        "is_selected",
                        "updated_at",
                    ]
                )

        recalc_required = True

        message = f"Reverted {len(results)} candidates to their stored result status."

    if recalc_required:
        status_application = apply_semester_result_statuses(
            department=configuration.department,
            semester=configuration.semester,
            threshold_value=threshold_mapping.min_threshold_mark,
            seat_limit=threshold_mapping.seat_limit,
            waiting_student_limit=threshold_mapping.waiting_student_limit,
        )
        if not status_application.get("success"):
            return Response(
                {
                    "success": False,
                    "message": status_application.get(
                        "error",
                        "Failed to apply override recalculation",
                    ),
                    "configuration_missing": status_application.get("configuration_missing", False),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    refreshed = AdmissionResult.objects.filter(configuration=configuration)
    return Response(
        {
            "success": True,
            "message": message,
            "summary": summarize_status_counts(refreshed),
        }
    )


@extend_schema(
    operation_id="set_admission_result_viva_status",
    tags=["Admission Management"],
    summary="Toggle a candidate's viva given/not-given display flag",
    description=(
        "Display-only flag for the results board: when false the Viva column "
        "shows 'Not Given'. Never touches marks, weighted totals, or selection."
    ),
    responses={200: OpenApiResponse(description="Viva status updated")},
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def set_admission_result_viva_status(request, result_id):
    viva_given = request.data.get("viva_given")
    if not isinstance(viva_given, bool):
        return Response(
            {"success": False, "message": "viva_given must be a boolean."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    result = AdmissionResult.objects.filter(id=result_id).first()
    if not result:
        return Response(
            {"success": False, "message": "Admission result not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    result.viva_given = viva_given
    result.save(update_fields=["viva_given", "updated_at"])
    return Response({"success": True, "viva_given": result.viva_given})


@extend_schema(
    operation_id="get_admission_result_by_id",
    tags=["Admission Management"],
    summary="Get specific admission result by ID",
    responses={200: AdmissionResultSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_admission_result_by_id(request, result_id):
    try:
        result = AdmissionResult.objects.select_related(
            "exam",
            "student",
            "department",
            "configuration",
            "configuration__department",
            "configuration__exam",
        ).get(id=result_id)
    except AdmissionResult.DoesNotExist:
        return Response(
            {"success": False, "message": "Admission result not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = AdmissionResultSerializer(result)
    return Response({"success": True, "data": serializer.data})


@extend_schema(
    operation_id="get_student_admission_result",
    tags=["Admission Management"],
    summary="Get admission result for a specific student in an exam",
    responses={200: AdmissionResultSerializer},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_student_admission_result(request, exam_id, student_id):
    try:
        result = AdmissionResult.objects.select_related(
            "exam",
            "student",
            "department",
            "configuration",
            "configuration__department",
            "configuration__exam",
        ).get(exam_id=exam_id, student_id=student_id)
    except AdmissionResult.DoesNotExist:
        return Response(
            {
                "success": False,
                "message": f"No admission result found for student {student_id} in exam {exam_id}",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = AdmissionResultSerializer(result)
    return Response({"success": True, "data": serializer.data})


@extend_schema(
    operation_id="publish_admission_results",
    tags=["Admission Management"],
    summary="Publish admission results",
    request=CalculateAdmissionResultsSerializer,
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def publish_admission_results(request):
    serializer = CalculateAdmissionResultsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Invalid request data", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    exam_id = serializer.validated_data["exam_id"]
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return Response(
            {"success": False, "message": f"Exam with ID {exam_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    with transaction.atomic():
        updated_count = AdmissionResult.objects.filter(exam=exam, status="PENDING").update(
            status="PUBLISHED"
        )

    if updated_count == 0:
        return Response(
            {"success": False, "message": "No pending results found for this exam"},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "success": True,
            "message": f"Published {updated_count} admission results for exam {exam_id}",
            "published_count": updated_count,
            "exam_id": exam_id,
        }
    )


@extend_schema(
    operation_id="recalculate_student_result",
    tags=["Admission Management"],
    summary="Recalculate result for a single student",
    responses={200: AdmissionResultSerializer},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def recalculate_student_result(request, exam_id, student_id):
    result = recalculate_single_student_result(exam_id, student_id)

    if not result["success"]:
        return Response(
            {
                "success": False,
                "message": result.get("error", "Failed to recalculate result"),
                "configuration_missing": result.get("configuration_missing", False),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        admission_result = AdmissionResult.objects.select_related(
            "exam",
            "student",
            "department",
            "configuration",
            "configuration__department",
            "configuration__exam",
        ).get(exam_id=exam_id, student_id=student_id)
    except AdmissionResult.DoesNotExist:
        return Response(
            {"success": False, "message": "Failed to retrieve recalculated result"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = AdmissionResultSerializer(admission_result)
    return Response(
        {
            "success": True,
            "message": f"Result updated successfully for student {result['student']}",
            "data": serializer.data,
        }
    )


RESULT_STATUS_KEYS = ["SELECTED", "WAITING", "REJECTED", "ABSENT"]
PUBLICATION_STATUS_KEYS = ["PENDING", "PUBLISHED", "CANCELLED"]


@extend_schema(
    operation_id="admission_dashboard_stats",
    tags=["Admission Management"],
    summary="Aggregated admission statistics for the dashboard",
    parameters=[
        OpenApiParameter(name="days", required=False, type=int),
        OpenApiParameter(name="semester", required=False, type=str),
        OpenApiParameter(name="department_id", required=False, type=int),
    ],
    responses={200: OpenApiResponse(description="Dashboard statistics")},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def admission_dashboard_stats(request):
    """
    Return admission-result aggregates for the dashboard:
      - daily: result counts per creation day, split by result_status
      - status_totals / publication_totals: overall breakdowns
      - by_department: selected vs total per department (top 8)
      - totals: headline KPI numbers
    All aggregates respect the optional semester / department_id filters; the
    daily series is additionally limited to the last `days` days (default 30).
    """
    try:
        days = int(request.query_params.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))

    semester = request.query_params.get("semester")
    department_id = request.query_params.get("department_id")

    base_qs = AdmissionResult.objects.all()
    if semester:
        semester = normalize_semester_filter(semester)
        base_qs = base_qs.filter(
            Q(configuration__semester__iexact=semester) | Q(exam__semester__iexact=semester)
        )
    if department_id:
        base_qs = base_qs.filter(department_id=department_id)

    # --- Daily series (by creation date), split by result_status ---
    start_date = (timezone.now() - timedelta(days=days - 1)).date()
    window_qs = base_qs.filter(created_at__date__gte=start_date)

    daily_map = {}
    daily_rows = (
        window_qs.annotate(day=TruncDate("created_at"))
        .values("day", "result_status")
        .annotate(count=Count("id"))
    )
    for row in daily_rows:
        day = row["day"]
        if not day:
            continue
        key = day.isoformat()
        entry = daily_map.setdefault(
            key,
            {"date": key, "SELECTED": 0, "WAITING": 0, "REJECTED": 0, "ABSENT": 0, "total": 0},
        )
        status_key = (row["result_status"] or "WAITING").upper()
        if status_key not in RESULT_STATUS_KEYS:
            status_key = "WAITING"
        entry[status_key] += row["count"]
        entry["total"] += row["count"]

    # Only return days that actually have results, ordered chronologically.
    daily = [daily_map[key] for key in sorted(daily_map.keys())]

    # --- Status totals (all-time within filters) ---
    status_totals = {key: 0 for key in RESULT_STATUS_KEYS}
    for row in base_qs.values("result_status").annotate(count=Count("id")):
        status_key = (row["result_status"] or "WAITING").upper()
        if status_key not in status_totals:
            status_key = "WAITING"
        status_totals[status_key] += row["count"]

    # --- Publication status totals ---
    publication_totals = {key: 0 for key in PUBLICATION_STATUS_KEYS}
    for row in base_qs.values("status").annotate(count=Count("id")):
        status_key = (row["status"] or "PENDING").upper()
        if status_key not in publication_totals:
            status_key = "PENDING"
        publication_totals[status_key] += row["count"]

    # --- Per-department breakdown (top 8 by total) ---
    dept_rows = (
        base_qs.values("department__department_shortname", "department__department_name")
        .annotate(
            total=Count("id"),
            selected=Count("id", filter=Q(result_status="SELECTED")),
        )
        .order_by("-total")[:8]
    )
    by_department = [
        {
            "department": (
                row["department__department_shortname"]
                or row["department__department_name"]
                or "Unassigned"
            ),
            "department_name": row["department__department_name"] or "Unassigned",
            "total": row["total"],
            "selected": row["selected"],
        }
        for row in dept_rows
    ]

    totals = {
        "total_results": base_qs.count(),
        "selected": status_totals["SELECTED"],
        "waiting": status_totals["WAITING"],
        "rejected": status_totals["REJECTED"],
        "absent": status_totals["ABSENT"],
        "admitted": base_qs.filter(is_admitted=True).count(),
        "attended": base_qs.filter(attended_exam=True).count(),
        "published": publication_totals["PUBLISHED"],
    }

    return Response(
        {
            "success": True,
            "days": days,
            "daily": daily,
            "status_totals": status_totals,
            "publication_totals": publication_totals,
            "by_department": by_department,
            "totals": totals,
        }
    )
