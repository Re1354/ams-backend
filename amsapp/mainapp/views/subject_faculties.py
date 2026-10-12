from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models.subject_faculty import SubjectFaculty
from ..models.subjects import Subject
from ..models.faculty import Faculty
from ..permissions import require_menu_permission
from ..serializers.subject import SubjectFacultySerializer, SubjectFacultyCreateSerializer
from ..services.access_control import get_user_access_scope, get_faculty_for_department


@extend_schema(
    operation_id='get_all_subject_faculties',
    tags=['Subject-Faculty Mapping'],
    summary="Get all faculty-subject mappings",
    description="Retrieve all faculty-subject mappings with subject details.",
    responses={
        200: OpenApiResponse(
            response=SubjectFacultySerializer(many=True),
            description="List of all faculty-subject mappings"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_subject_faculties(request):
    """Get all faculty-subject mappings based on access control scope."""
    user = request.user
    custom_user = user.custom_user if hasattr(user, 'custom_user') else None
    scope = get_user_access_scope(custom_user)

    if scope['is_global']:
        mappings = SubjectFaculty.objects.select_related('faculty').all().order_by('faculty__faculty_name')
    elif scope['access_type'] == 'FACULTY' and custom_user and custom_user.faculty_id:
        mappings = SubjectFaculty.objects.select_related('faculty').filter(faculty_id=custom_user.faculty_id).order_by('faculty__faculty_name')
    elif scope['access_type'] == 'DEPARTMENT' and custom_user and custom_user.department_id:
        parent_faculty = get_faculty_for_department(custom_user.department_id)
        if parent_faculty:
            mappings = SubjectFaculty.objects.select_related('faculty').filter(faculty=parent_faculty).order_by('faculty__faculty_name')
        else:
            mappings = SubjectFaculty.objects.none()
    else:
        mappings = SubjectFaculty.objects.none()

    serializer = SubjectFacultySerializer(mappings, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Subject-faculty mappings retrieved successfully'
    })


@extend_schema(
    tags=['Subject-Faculty Mapping'],
    summary="Create faculty-subject mapping",
    description="Create a new faculty with assigned subjects. Requires subject-department mapping write permission.",
    responses={
        201: OpenApiResponse(
            response=SubjectFacultySerializer,
            description="Faculty-subject mapping created successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing permission")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subject_faculty(request):
    """Create faculty-subject mapping."""
    denied = require_menu_permission(
        request,
        "/subject-department-mapping",
        "write",
        "You do not have permission to create faculty-subject mappings.",
    )
    if denied:
        return denied
    
    serializer = SubjectFacultyCreateSerializer(data=request.data)
    if serializer.is_valid():
        mapping = serializer.save()
        response_serializer = SubjectFacultySerializer(mapping)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Faculty "{mapping.faculty.faculty_name}" with subjects created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_subject_faculty_by_id',
    tags=['Subject-Faculty Mapping'],
    summary="Get faculty-subject mapping by ID",
    description="Retrieve a specific faculty-subject mapping by its ID.",
    responses={
        200: OpenApiResponse(
            response=SubjectFacultySerializer,
            description="Faculty-subject mapping details"
        ),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subject_faculty_by_id(request, mapping_id):
    """Get faculty-subject mapping by ID."""
    mapping = get_object_or_404(SubjectFaculty, id=mapping_id)
    user = request.user
    custom_user = user.custom_user if hasattr(user, 'custom_user') else None
    scope = get_user_access_scope(custom_user)
    
    if not scope['is_global']:
        if scope['access_type'] == 'FACULTY' and custom_user.faculty_id != mapping.faculty_id:
            return Response({"success": False, "message": "You do not have access to this faculty."}, status=403)
        elif scope['access_type'] == 'DEPARTMENT' and custom_user.department_id:
            parent_faculty = get_faculty_for_department(custom_user.department_id)
            if not parent_faculty or parent_faculty.id != mapping.faculty_id:
                return Response({"success": False, "message": "You do not have access to this faculty."}, status=403)

    serializer = SubjectFacultySerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Faculty-subject mapping retrieved successfully'
    })


@extend_schema(
    tags=['Subject-Faculty Mapping'],
    summary="Get subjects by faculty ID",
    description="Retrieve subjects assigned to a specific faculty.",
    responses={
        200: OpenApiResponse(
            response=SubjectFacultySerializer,
            description="Faculty subjects"
        ),
        404: OpenApiResponse(description="Faculty mapping not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subjects_by_faculty(request, faculty_id):
    """Get subjects by faculty ID."""
    mapping = get_object_or_404(SubjectFaculty, faculty_id=faculty_id)
    serializer = SubjectFacultySerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Subjects for faculty retrieved successfully'
    })


@extend_schema(
    tags=['Subject-Faculty Mapping'],
    summary="Update faculty-subject mapping",
    description="Update faculty or assigned subjects. Requires subject-department mapping edit permission.",
    responses={
        200: OpenApiResponse(
            response=SubjectFacultySerializer,
            description="Faculty-subject mapping updated successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing edit permission"),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_subject_faculty(request, mapping_id):
    """Update faculty-subject mapping."""
    denied = require_menu_permission(
        request,
        "/subject-department-mapping",
        "edit",
        "You do not have permission to edit faculty-subject mappings.",
    )
    if denied:
        return denied
    
    mapping = get_object_or_404(SubjectFaculty, id=mapping_id)
    partial = request.method == 'PATCH'
    serializer = SubjectFacultyCreateSerializer(mapping, data=request.data, partial=partial)
    
    if serializer.is_valid():
        mapping = serializer.save()
        response_serializer = SubjectFacultySerializer(mapping)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Faculty "{mapping.faculty.faculty_name}" mapping updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Subject-Faculty Mapping'],
    summary="Add subjects to faculty",
    description="Add additional subjects to an existing faculty. Requires edit permission.",
    responses={
        200: OpenApiResponse(
            response=SubjectFacultySerializer,
            description="Subjects added to faculty successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        404: OpenApiResponse(description="Faculty mapping not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_subjects_to_faculty(request, mapping_id):
    """Add subjects to existing faculty mapping."""
    denied = require_menu_permission(
        request,
        "/subject-department-mapping",
        "edit",
        "You do not have permission to edit faculty-subject mappings.",
    )
    if denied:
        return denied
    
    mapping = get_object_or_404(SubjectFaculty, id=mapping_id)
    new_subject_ids = request.data.get('subject_ids', [])
    
    if not new_subject_ids:
        return Response({
            'success': False,
            'message': 'subject_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    existing_subjects = Subject.objects.filter(id__in=new_subject_ids)
    existing_ids = list(existing_subjects.values_list('id', flat=True))
    
    for subject_id in new_subject_ids:
        if subject_id not in existing_ids:
            return Response({
                'success': False,
                'message': f'Subject with ID {subject_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    current_subjects = set(mapping.subject_ids or [])
    new_subjects = set(new_subject_ids)
    mapping.subject_ids = list(current_subjects.union(new_subjects))
    mapping.save()
    
    serializer = SubjectFacultySerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Subjects added to faculty "{mapping.faculty.faculty_name}" successfully'
    })


@extend_schema(
    tags=['Subject-Faculty Mapping'],
    summary="Remove subjects from faculty",
    description="Remove subjects from an existing faculty.",
    responses={
        200: OpenApiResponse(
            response=SubjectFacultySerializer,
            description="Subjects removed successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        404: OpenApiResponse(description="Faculty mapping not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remove_subjects_from_faculty(request, mapping_id):
    """Remove subjects from existing faculty mapping."""
    denied = require_menu_permission(
        request,
        "/subject-department-mapping",
        "edit",
        "You do not have permission to edit faculty-subject mappings.",
    )
    if denied:
        return denied
    
    mapping = get_object_or_404(SubjectFaculty, id=mapping_id)
    remove_subject_ids = request.data.get('subject_ids', [])
    
    if not remove_subject_ids:
        return Response({
            'success': False,
            'message': 'subject_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    current_subjects = set(mapping.subject_ids or [])
    subjects_to_remove = set(remove_subject_ids)
    mapping.subject_ids = list(current_subjects - subjects_to_remove)
    mapping.save()
    
    serializer = SubjectFacultySerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Subjects removed from faculty "{mapping.faculty.faculty_name}" successfully'
    })


@extend_schema(
    tags=['Subject-Faculty Mapping'],
    summary="Delete faculty-subject mapping",
    description="Delete a faculty-subject mapping. Requires delete permission.",
    responses={
        200: OpenApiResponse(description="Faculty-subject mapping deleted successfully"),
        403: OpenApiResponse(description="Missing permission"),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_subject_faculty(request, mapping_id):
    """Delete faculty-subject mapping."""
    denied = require_menu_permission(
        request,
        "/subject-department-mapping",
        "delete",
        "You do not have permission to delete faculty-subject mappings.",
    )
    if denied:
        return denied
    
    mapping = get_object_or_404(SubjectFaculty, id=mapping_id)
    faculty_name = mapping.faculty.faculty_name
    subject_count = len(mapping.subject_ids or [])
    
    mapping.delete()
    
    return Response({
        'success': True,
        'message': f'Faculty "{faculty_name}" mapping deleted successfully',
        'note': f'This removed {subject_count} subject assignments'
    })
