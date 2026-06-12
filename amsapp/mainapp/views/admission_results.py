from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema

from ..authentication import CustomJWTAuthentication
from ..models import AdmissionConfiguration, AdmissionResult, Department, DepartmentThreshold, Exam
from ..serializers.admission_result import (
    AdmissionConfigurationSerializer,
    AdmissionConfigurationUpsertSerializer,
    AdmissionResultSerializer,
    BulkAdmissionStatusUpdateSerializer,
    CalculateAdmissionResultsSerializer,
    CalculateResultsResponseSerializer,
)
from ..services.admission_calculator import (
    apply_semester_result_statuses,
    calculate_admission_results,
    calculate_semester_admission_results,
    get_threshold_mapping_for_semester,
    get_or_create_admission_configuration,
    get_candidate_students_for_exam,
    is_configuration_complete,
    recalculate_single_student_result,
    resolve_department_for_exam,
    summarize_status_counts,
)
from ..utils import normalize_semester_filter, semester_sort_key


class AdmissionResultsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def get_single_configuration(filters):
    config_ids = list(
        filters.exclude(configuration__isnull=True)
        .values_list("configuration_id", flat=True)
        .distinct()[:2]
    )
    if len(config_ids) == 1:
        return AdmissionConfiguration.objects.filter(id=config_ids[0]).first()
    return None


def resolve_reverted_status(result):
    if not result.attended_exam:
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
        and result.weighted_total_marks >= float(threshold_value)
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
    if "threshold" in validated_data:
        configuration.threshold = validated_data["threshold"]
        updates.append("threshold")
    if "notes" in validated_data:
        configuration.notes = validated_data["notes"]
        updates.append("notes")

    if updates:
        configuration.save(update_fields=updates + ["updated_at"])

    if "seat_limit" in validated_data or "threshold" in validated_data:
        DepartmentThreshold.objects.update_or_create(
            semester=configuration.semester,
            department=configuration.department,
            defaults={
                "min_threshold_mark": configuration.threshold,
                "seat_limit": configuration.seat_limit,
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
    if not department or not semester:
        return

    threshold_mapping = get_threshold_mapping_for_semester(department, semester)
    if not is_configuration_complete(threshold_mapping):
        return

    semester_exams = list(
        get_exam_queryset_for_department_semester(department=department, semester=semester)
    )
    if not semester_exams:
        return

    has_results = AdmissionResult.objects.filter(exam__in=semester_exams).exists()
    if has_results:
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
    if request.method == "GET":
        queryset = AdmissionConfiguration.objects.select_related("department", "exam").all()
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

    configuration, _, error = resolve_configuration_from_payload(serializer.validated_data)
    if error:
        return Response(
            {"success": False, "message": error},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if any(field in serializer.validated_data for field in ("seat_limit", "threshold")):
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

    for field in ("seat_limit", "threshold", "notes"):
        if field in serializer.validated_data:
            setattr(configuration, field, serializer.validated_data[field])
    configuration.save()

    if any(field in serializer.validated_data for field in ("seat_limit", "threshold")):
        DepartmentThreshold.objects.update_or_create(
            semester=configuration.semester,
            department=configuration.department,
            defaults={
                "min_threshold_mark": configuration.threshold,
                "seat_limit": configuration.seat_limit,
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
    department_id = request.query_params.get("department_id")
    department = None

    if department_id:
        department = Department.objects.filter(id=department_id).first()
        if not department:
            return Response(
                {"success": False, "message": "Department not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    exam_semesters = list(
        get_exam_queryset_for_department_semester(department=department)
        .order_by("semester")
        .values_list("semester", flat=True)
        .distinct()
    )
    semesters = sorted(set(exam_semesters), key=semester_sort_key)
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
        OpenApiParameter(name="page", required=False, type=int),
        OpenApiParameter(name="page_size", required=False, type=int),
    ],
    responses={200: AdmissionResultSerializer(many=True)},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_admission_results(request):
    results = AdmissionResult.objects.select_related(
        "exam",
        "student",
        "department",
        "configuration",
        "configuration__department",
        "configuration__exam",
    ).all()

    exam_id = request.query_params.get("exam_id")
    configuration_id = request.query_params.get("configuration_id")
    department_id = request.query_params.get("department_id")
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

    if exam_id:
        results = results.filter(exam_id=exam_id)
    if configuration_id:
        results = results.filter(configuration_id=configuration_id)
    if department_id:
        results = results.filter(department_id=department_id)
    if student_id:
        results = results.filter(student_id=student_id)
    if semester:
        semester = normalize_semester_filter(semester)
        resolved_department = (
            Department.objects.filter(id=department_id).first() if department_id else None
        )
        ensure_semester_admission_results(
            department=resolved_department,
            semester=semester,
        )
        if resolved_department:
            threshold_mapping = get_threshold_mapping_for_semester(resolved_department, semester)
            configuration_missing = not is_configuration_complete(threshold_mapping)
        results = AdmissionResult.objects.select_related(
            "exam",
            "student",
            "department",
            "configuration",
            "configuration__department",
            "configuration__exam",
        ).all()
        if exam_id:
            results = results.filter(exam_id=exam_id)
        if configuration_id:
            results = results.filter(configuration_id=configuration_id)
        if department_id:
            results = results.filter(department_id=department_id)
        if student_id:
            results = results.filter(student_id=student_id)
        results = results.filter(
            Q(configuration__semester__iexact=semester) | Q(exam__semester__iexact=semester)
        )
    if search:
        results = results.filter(
            Q(student__username__icontains=search)
            | Q(student__full_name__icontains=search)
            | Q(student__f_id__icontains=search)
        )
    if is_selected is not None:
        results = results.filter(is_selected=is_selected.lower() in {"true", "1", "yes"})
    if attended_exam is not None:
        results = results.filter(attended_exam=attended_exam.lower() in {"true", "1", "yes"})
    if publication_status:
        results = results.filter(status__iexact=publication_status)

    summary_queryset = results
    summary = summarize_status_counts(summary_queryset)
    configuration = get_single_configuration(summary_queryset)

    if result_status:
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
        "name": f"{order_prefix}student__full_name",
        "score": f"{order_prefix}weighted_total_marks",
        "form_id": f"{order_prefix}student__f_id",
        "serial": f"{order_prefix}id",
    }
    results = results.order_by(sort_mapping.get(sort_by, "-weighted_total_marks"), "-created_at")

    paginator = AdmissionResultsPagination()
    page = paginator.paginate_queryset(results, request)
    serializer = AdmissionResultSerializer(page if page is not None else results, many=True)

    if page is not None:
        response = paginator.get_paginated_response(serializer.data)
        response.data["success"] = True
        response.data["summary"] = summary
        response.data["configuration"] = (
            AdmissionConfigurationSerializer(configuration).data if configuration else None
        )
        response.data["configuration_missing"] = configuration_missing
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
        }
        return response

    return Response(
        {
            "success": True,
            "count": results.count(),
            "summary": summary,
            "configuration": (
                AdmissionConfigurationSerializer(configuration).data if configuration else None
            ),
            "configuration_missing": configuration_missing,
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

    queryset = AdmissionResult.objects.select_related("configuration").filter(student_id__in=student_ids)
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

    if action == "SET_STATUS":
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
                queryset.update(result_status=target_status, is_override_accepted=True)
            else:
                queryset.update(
                    result_status=target_status,
                    is_override_accepted=False,
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
                result.is_selected = False
                result.save(
                    update_fields=[
                        "result_status",
                        "is_override_accepted",
                        "is_selected",
                        "updated_at",
                    ]
                )

        if had_override:
            recalc_required = True

        message = f"Reverted {len(results)} candidates to their stored result status."

    if recalc_required:
        status_application = apply_semester_result_statuses(
            department=configuration.department,
            semester=configuration.semester,
            threshold_value=threshold_mapping.min_threshold_mark,
            seat_limit=threshold_mapping.seat_limit,
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
