from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import Department, Subject, SubjectDepartment, SubjectPriority
from ..permissions import require_menu_permission
from ..serializers.subject_priority import (
    DepartmentSubjectPrioritySerializer,
    SubjectPriorityItemSerializer,
    SubjectPrioritySaveSerializer,
)


@extend_schema(
    operation_id="get_all_subject_priorities",
    tags=["Subject Priority Mapping"],
    summary="Get all department subject priority mappings",
    description="Retrieve all configured department-wise subject priorities.",
    responses={
        200: OpenApiResponse(
            response=DepartmentSubjectPrioritySerializer(many=True),
            description="List of all departments and their configured subject priorities",
        )
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_subject_priorities(request):
    """Retrieve all departments with their configured subject priorities."""
    denied = require_menu_permission(
        request,
        "/subject-priority-mapping",
        "read",
        "You do not have permission to view subject priority mappings.",
    )
    if denied:
        return denied

    departments = Department.objects.all().order_by("department_name")
    priorities = SubjectPriority.objects.select_related("subject", "department").order_by(
        "department_id", "priority"
    )

    priorities_by_dept = {}
    for p in priorities:
        priorities_by_dept.setdefault(p.department_id, []).append(p)

    data = []
    for dept in departments:
        dept_priorities = priorities_by_dept.get(dept.id, [])
        data.append(
            {
                "department_id": dept.id,
                "department_name": dept.department_name,
                "department_shortname": dept.department_shortname,
                "priorities": SubjectPriorityItemSerializer(dept_priorities, many=True).data,
            }
        )

    return Response(
        {
            "success": True,
            "data": data,
            "message": "Subject priority mappings retrieved successfully",
        }
    )


@extend_schema(
    operation_id="get_department_subject_priority",
    tags=["Subject Priority Mapping"],
    summary="Get subject priorities for a specific department",
    description="Retrieve subject priorities and available subjects for a specific department.",
    responses={
        200: OpenApiResponse(
            description="Subject priority configuration for the department",
        )
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_department_subject_priority(request, department_id):
    """Retrieve subject priorities and available subjects for a department."""
    denied = require_menu_permission(
        request,
        "/subject-priority-mapping",
        "read",
        "You do not have permission to view subject priority mappings.",
    )
    if denied:
        return denied

    department = get_object_or_404(Department, id=department_id)
    priorities = (
        SubjectPriority.objects.filter(department=department)
        .select_related("subject")
        .order_by("priority")
    )

    # Get department-associated subjects if mapped, or all subjects
    subject_dept = SubjectDepartment.objects.filter(department=department).first()
    dept_subject_ids = set(subject_dept.subject_ids) if subject_dept and subject_dept.subject_ids else set()

    all_subjects = Subject.objects.all().order_by("subject_name")
    available_subjects = []
    for sub in all_subjects:
        available_subjects.append(
            {
                "id": sub.id,
                "subject_name": sub.subject_name,
                "is_department_subject": sub.id in dept_subject_ids,
            }
        )

    return Response(
        {
            "success": True,
            "data": {
                "department_id": department.id,
                "department_name": department.department_name,
                "department_shortname": department.department_shortname,
                "priorities": SubjectPriorityItemSerializer(priorities, many=True).data,
                "available_subjects": available_subjects,
            },
            "message": "Department subject priority retrieved successfully",
        }
    )


@extend_schema(
    operation_id="save_department_subject_priority",
    tags=["Subject Priority Mapping"],
    summary="Save or update subject priority mapping for a department",
    description="Configure sequential subject priority order for a department.",
    request=SubjectPrioritySaveSerializer,
    responses={
        200: OpenApiResponse(description="Subject priority mapping updated successfully"),
        400: OpenApiResponse(description="Validation error"),
        403: OpenApiResponse(description="Permission denied"),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_department_subject_priority(request):
    """Save or update sequential subject priority mapping for a department."""
    denied = require_menu_permission(
        request,
        "/subject-priority-mapping",
        "write",
        "You do not have permission to configure subject priority mappings.",
    )
    if denied:
        return denied

    serializer = SubjectPrioritySaveSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {
                "success": False,
                "errors": serializer.errors,
                "message": "Invalid subject priority configuration",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    department_id = serializer.validated_data["department_id"]
    subject_ids = serializer.validated_data["subject_ids"]

    department = get_object_or_404(Department, id=department_id)

    with transaction.atomic():
        # Clear existing priorities
        SubjectPriority.objects.filter(department=department).delete()

        new_priorities = []
        for index, subject_id in enumerate(subject_ids, start=1):
            subject = Subject.objects.get(id=subject_id)
            new_priorities.append(
                SubjectPriority(
                    department=department,
                    subject=subject,
                    priority=index,
                )
            )

        if new_priorities:
            SubjectPriority.objects.bulk_create(new_priorities)

    updated_priorities = (
        SubjectPriority.objects.filter(department=department)
        .select_related("subject")
        .order_by("priority")
    )

    return Response(
        {
            "success": True,
            "data": {
                "department_id": department.id,
                "department_name": department.department_name,
                "department_shortname": department.department_shortname,
                "priorities": SubjectPriorityItemSerializer(updated_priorities, many=True).data,
            },
            "message": f"Subject priorities for {department.department_shortname or department.department_name} saved successfully",
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    operation_id="delete_department_subject_priority",
    tags=["Subject Priority Mapping"],
    summary="Delete/reset subject priority mapping for a department",
    description="Remove all configured subject priorities for a department.",
    responses={
        200: OpenApiResponse(description="Subject priorities reset successfully"),
        403: OpenApiResponse(description="Permission denied"),
    },
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_department_subject_priority(request, department_id):
    """Delete/reset all subject priority mapping for a department."""
    denied = require_menu_permission(
        request,
        "/subject-priority-mapping",
        "delete",
        "You do not have permission to delete subject priority mappings.",
    )
    if denied:
        return denied

    department = get_object_or_404(Department, id=department_id)
    count, _ = SubjectPriority.objects.filter(department=department).delete()

    return Response(
        {
            "success": True,
            "message": f"Subject priorities for {department.department_shortname or department.department_name} reset successfully ({count} rules removed)",
        }
    )
