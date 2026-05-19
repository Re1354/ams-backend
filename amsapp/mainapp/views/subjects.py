from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models import Subject
from ..permissions import require_menu_permission
from ..serializers import SubjectSerializer


@extend_schema(
    operation_id='get_all_subjects',
    tags=['Subjects'],
    summary="Get all subjects",
    description="Retrieve all subjects in the system.",
    responses={
        200: OpenApiResponse(
            response=SubjectSerializer(many=True),
            description="List of all subjects"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_subjects(request):
    """Get all subjects"""
    subjects = Subject.objects.all().order_by('subject_name')
    serializer = SubjectSerializer(subjects, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Subjects retrieved successfully'
    })


@extend_schema(
    tags=['Subjects'],
    summary="Create a new subject",
    description="Create a new subject. Requires subject management write permission.",
    request=SubjectSerializer,
    responses={
        201: OpenApiResponse(
            response=SubjectSerializer,
            description="Subject created successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing subject create permission")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subject(request):
    """Create a new subject."""

    denied = require_menu_permission(
        request,
        "/subject-management",
        "write",
        "You do not have permission to create subjects.",
    )
    if denied:
        return denied
    
    serializer = SubjectSerializer(data=request.data)
    if serializer.is_valid():
        subject = serializer.save()
        return Response({
            'success': True,
            'data': serializer.data,
            'message': f'Subject "{subject.subject_name}" created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_subject_by_id',
    tags=['Subjects'],
    summary="Get subject by ID",
    description="Retrieve a specific subject by its ID.",
    responses={
        200: OpenApiResponse(
            response=SubjectSerializer,
            description="Subject details"
        ),
        404: OpenApiResponse(description="Subject not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subject_by_id(request, subject_id):
    """Get subject by ID"""
    subject = get_object_or_404(Subject, id=subject_id)
    serializer = SubjectSerializer(subject)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Subject retrieved successfully'
    })


@extend_schema(
    tags=['Subjects'],
    summary="Update subject",
    description="Update subject details. Requires subject management edit permission.",
    request=SubjectSerializer,
    responses={
        200: OpenApiResponse(
            response=SubjectSerializer,
            description="Subject updated successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing subject edit permission"),
        404: OpenApiResponse(description="Subject not found")
    }
)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_subject(request, subject_id):
    """Update subject."""

    denied = require_menu_permission(
        request,
        "/subject-management",
        "edit",
        "You do not have permission to edit subjects.",
    )
    if denied:
        return denied
    
    subject = get_object_or_404(Subject, id=subject_id)
    
    # Use partial=True for PATCH requests
    partial = request.method == 'PATCH'
    serializer = SubjectSerializer(subject, data=request.data, partial=partial)
    
    if serializer.is_valid():
        subject = serializer.save()
        return Response({
            'success': True,
            'data': serializer.data,
            'message': f'Subject "{subject.subject_name}" updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Subjects'],
    summary="Delete subject",
    description="Delete a subject. Requires subject management delete permission. Warning: This may affect department-subject mappings.",
    responses={
        200: OpenApiResponse(description="Subject deleted successfully"),
        403: OpenApiResponse(description="Missing subject delete permission"),
        404: OpenApiResponse(description="Subject not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_subject(request, subject_id):
    """Delete subject."""

    denied = require_menu_permission(
        request,
        "/subject-management",
        "delete",
        "You do not have permission to delete subjects.",
    )
    if denied:
        return denied
    
    subject = get_object_or_404(Subject, id=subject_id)
    subject_name = subject.subject_name
    
    # Check if subject is used in department mappings
    from ..models import SubjectDepartment
    departments_using_subject = SubjectDepartment.objects.filter(
        subject_ids__contains=[subject_id]
    )
    
    # Delete the subject
    subject.delete()
    
    message = f'Subject "{subject_name}" deleted successfully'
    if departments_using_subject.exists():
        dept_names = list(departments_using_subject.values_list('department_name', flat=True))
        message += f'. Note: This subject was removed from departments: {", ".join(dept_names)}'
    
    return Response({
        'success': True,
        'message': message
    })
