from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models.faculties_departments import FacultyDepartment
from ..models.faculty import Faculty
from ..models.departments import Department
from ..permissions import require_menu_permission
from ..serializers.faculty_department import FacultyDepartmentSerializer, FacultyDepartmentCreateSerializer


@extend_schema(
    operation_id='get_all_faculty_departments',
    tags=['Faculty-Department Mapping'],
    summary="Get all faculty-department mappings",
    description="Retrieve all faculty-department mappings with department details.",
    responses={
        200: OpenApiResponse(
            response=FacultyDepartmentSerializer(many=True),
            description="List of all faculty-department mappings"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_faculty_departments(request):
    """Get all faculty-department mappings"""
    mappings = FacultyDepartment.objects.select_related('faculty').all().order_by('faculty__faculty_name')
    serializer = FacultyDepartmentSerializer(mappings, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Faculty-department mappings retrieved successfully'
    })


@extend_schema(
    tags=['Faculty-Department Mapping'],
    summary="Create faculty-department mapping",
    description="Create a new faculty with assigned departments. Requires faculty-department mapping write permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'faculty': {'type': 'integer', 'description': 'Faculty ID'},
                'department_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of department IDs to assign to faculty'
                }
            },
            'required': ['faculty'],
            'example': {
                'faculty': 1,
                'department_ids': [1, 2, 3]
            }
        }
    },
    responses={
        201: OpenApiResponse(
            response=FacultyDepartmentSerializer,
            description="Faculty-department mapping created successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty-department mapping create permission")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_faculty_department(request):
    """Create faculty-department mapping."""
    denied = require_menu_permission(
        request,
        "/faculty-department-mapping",
        "write",
        "You do not have permission to create faculty-department mappings.",
    )
    if denied:
        return denied

    serializer = FacultyDepartmentCreateSerializer(data=request.data)
    if serializer.is_valid():
        mapping = serializer.save()
        response_serializer = FacultyDepartmentSerializer(mapping)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Faculty "{mapping.faculty.faculty_name}" with departments created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_faculty_department_by_id',
    tags=['Faculty-Department Mapping'],
    summary="Get faculty-department mapping by ID",
    description="Retrieve a specific faculty-department mapping by its ID.",
    responses={
        200: OpenApiResponse(
            response=FacultyDepartmentSerializer,
            description="Faculty-department mapping details"
        ),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_faculty_department_by_id(request, mapping_id):
    """Get faculty-department mapping by ID"""
    mapping = get_object_or_404(FacultyDepartment, id=mapping_id)
    serializer = FacultyDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Faculty-department mapping retrieved successfully'
    })


@extend_schema(
    tags=['Faculty-Department Mapping'],
    summary="Get departments by faculty ID",
    description="Retrieve departments assigned to a specific faculty.",
    responses={
        200: OpenApiResponse(
            response=FacultyDepartmentSerializer,
            description="Faculty departments"
        ),
        404: OpenApiResponse(description="Faculty mapping not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_departments_by_faculty(request, faculty_id):
    """Get departments by faculty ID"""
    try:
        mapping = FacultyDepartment.objects.get(faculty_id=faculty_id)
        serializer = FacultyDepartmentSerializer(mapping)
        data = serializer.data
    except FacultyDepartment.DoesNotExist:
        faculty = get_object_or_404(Faculty, id=faculty_id)
        data = {
            'id': None,
            'faculty': faculty.id,
            'faculty_name': faculty.faculty_name,
            'department_ids': [],
            'departments': [],
            'departments_count': 0,
        }
    return Response({
        'success': True,
        'data': data,
        'message': 'Departments for faculty retrieved successfully'
    })


@extend_schema(
    tags=['Faculty-Department Mapping'],
    summary="Update faculty-department mapping",
    description="Update faculty or assigned departments. Requires faculty-department mapping edit permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'faculty': {'type': 'integer', 'description': 'Faculty ID'},
                'department_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of department IDs to assign to faculty'
                }
            },
            'example': {
                'faculty': 1,
                'department_ids': [1, 2, 3]
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=FacultyDepartmentSerializer,
            description="Faculty-department mapping updated successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty-department mapping edit permission"),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_faculty_department(request, mapping_id):
    """Update faculty-department mapping."""
    denied = require_menu_permission(
        request,
        "/faculty-department-mapping",
        "edit",
        "You do not have permission to edit faculty-department mappings.",
    )
    if denied:
        return denied

    mapping = get_object_or_404(FacultyDepartment, id=mapping_id)
    partial = request.method == 'PATCH'
    serializer = FacultyDepartmentCreateSerializer(mapping, data=request.data, partial=partial)

    if serializer.is_valid():
        mapping = serializer.save()
        response_serializer = FacultyDepartmentSerializer(mapping)
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
    tags=['Faculty-Department Mapping'],
    summary="Add departments to faculty",
    description="Add additional departments to an existing faculty. Requires faculty-department mapping edit permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'department_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of department IDs to add to faculty'
                }
            },
            'required': ['department_ids'],
            'example': {
                'department_ids': [4, 5]
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=FacultyDepartmentSerializer,
            description="Departments added to faculty successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty-department mapping edit permission"),
        404: OpenApiResponse(description="Faculty mapping not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_departments_to_faculty(request, mapping_id):
    """Add departments to existing faculty."""
    denied = require_menu_permission(
        request,
        "/faculty-department-mapping",
        "edit",
        "You do not have permission to edit faculty-department mappings.",
    )
    if denied:
        return denied

    mapping = get_object_or_404(FacultyDepartment, id=mapping_id)
    new_department_ids = request.data.get('department_ids', [])

    if not new_department_ids:
        return Response({
            'success': False,
            'message': 'department_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    existing_departments = Department.objects.filter(id__in=new_department_ids)
    existing_ids = set(existing_departments.values_list('id', flat=True))

    for dept_id in new_department_ids:
        if dept_id not in existing_ids:
            return Response({
                'success': False,
                'message': f'Department with ID {dept_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)

    current_departments = set(mapping.department_ids or [])
    new_departments = set(new_department_ids)
    updated_departments = list(current_departments.union(new_departments))

    mapping.department_ids = updated_departments
    mapping.save()

    serializer = FacultyDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Departments added to faculty "{mapping.faculty.faculty_name}" successfully'
    })


@extend_schema(
    tags=['Faculty-Department Mapping'],
    summary="Remove departments from faculty",
    description="Remove departments from an existing faculty. Requires faculty-department mapping edit permission.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'department_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of department IDs to remove from faculty'
                }
            },
            'required': ['department_ids'],
            'example': {
                'department_ids': [2, 3]
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=FacultyDepartmentSerializer,
            description="Departments removed from faculty successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Missing faculty-department mapping edit permission"),
        404: OpenApiResponse(description="Faculty mapping not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remove_departments_from_faculty(request, mapping_id):
    """Remove departments from existing faculty."""
    denied = require_menu_permission(
        request,
        "/faculty-department-mapping",
        "edit",
        "You do not have permission to edit faculty-department mappings.",
    )
    if denied:
        return denied

    mapping = get_object_or_404(FacultyDepartment, id=mapping_id)
    remove_department_ids = request.data.get('department_ids', [])

    if not remove_department_ids:
        return Response({
            'success': False,
            'message': 'department_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    current_departments = set(mapping.department_ids or [])
    departments_to_remove = set(remove_department_ids)
    updated_departments = list(current_departments - departments_to_remove)

    mapping.department_ids = updated_departments
    mapping.save()

    serializer = FacultyDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Departments removed from faculty "{mapping.faculty.faculty_name}" successfully'
    })


@extend_schema(
    tags=['Faculty-Department Mapping'],
    summary="Delete faculty-department mapping",
    description="Delete a faculty-department mapping. Requires faculty-department mapping delete permission.",
    responses={
        200: OpenApiResponse(description="Faculty-department mapping deleted successfully"),
        403: OpenApiResponse(description="Missing faculty-department mapping delete permission"),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_faculty_department(request, mapping_id):
    """Delete faculty-department mapping."""
    denied = require_menu_permission(
        request,
        "/faculty-department-mapping",
        "delete",
        "You do not have permission to delete faculty-department mappings.",
    )
    if denied:
        return denied

    mapping = get_object_or_404(FacultyDepartment, id=mapping_id)
    faculty_name = mapping.faculty.faculty_name
    department_count = len(mapping.department_ids or [])

    mapping.delete()

    return Response({
        'success': True,
        'message': f'Faculty "{faculty_name}" mapping deleted successfully',
        'note': f'This removed {department_count} department assignments'
    })
