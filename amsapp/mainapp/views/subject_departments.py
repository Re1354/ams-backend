from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models.subjects_demartments import SubjectDepartment
from ..models.subjects import Subject
from ..models.departments import Department
from ..serializers.subject import SubjectDepartmentSerializer, SubjectDepartmentCreateSerializer


@extend_schema(
    operation_id='get_all_subject_departments',
    tags=['Subject-Department Mapping'],
    summary="Get all department-subject mappings",
    description="Retrieve all department-subject mappings with subject details.",
    responses={
        200: OpenApiResponse(
            response=SubjectDepartmentSerializer(many=True),
            description="List of all department-subject mappings"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_subject_departments(request):
    """Get all department-subject mappings"""
    mappings = SubjectDepartment.objects.select_related('department').all().order_by('department__department_name')
    serializer = SubjectDepartmentSerializer(mappings, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Subject-department mappings retrieved successfully'
    })


@extend_schema(
    tags=['Subject-Department Mapping'],
    summary="Create department-subject mapping",
    description="Create a new department with assigned subjects. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'department': {'type': 'integer', 'description': 'Department ID'},
                'subject_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of subject IDs to assign to department'
                }
            },
            'required': ['department'],
            'example': {
                'department': 1,
                'subject_ids': [1, 2, 3, 5]
            }
        }
    },
    responses={
        201: OpenApiResponse(
            response=SubjectDepartmentSerializer,
            description="Department-subject mapping created successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can create mappings")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_subject_department(request):
    """Create department-subject mapping (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can create department-subject mappings'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = SubjectDepartmentCreateSerializer(data=request.data)
    if serializer.is_valid():
        mapping = serializer.save()
        response_serializer = SubjectDepartmentSerializer(mapping)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Department "{mapping.department.department_name}" with subjects created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_subject_department_by_id',
    tags=['Subject-Department Mapping'],
    summary="Get department-subject mapping by ID",
    description="Retrieve a specific department-subject mapping by its ID.",
    responses={
        200: OpenApiResponse(
            response=SubjectDepartmentSerializer,
            description="Department-subject mapping details"
        ),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subject_department_by_id(request, mapping_id):
    """Get department-subject mapping by ID"""
    mapping = get_object_or_404(SubjectDepartment, id=mapping_id)
    serializer = SubjectDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Department-subject mapping retrieved successfully'
    })


@extend_schema(
    tags=['Subject-Department Mapping'],
    summary="Get subjects by department ID",
    description="Retrieve subjects assigned to a specific department.",
    responses={
        200: OpenApiResponse(
            response=SubjectDepartmentSerializer,
            description="Department subjects"
        ),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_subjects_by_department(request, department_id):
    """Get subjects by department ID"""
    mapping = get_object_or_404(SubjectDepartment, department_id=department_id)
    serializer = SubjectDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Subjects for department retrieved successfully'
    })


@extend_schema(
    tags=['Subject-Department Mapping'],
    summary="Update department-subject mapping",
    description="Update department or assigned subjects. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'department': {'type': 'integer', 'description': 'Department ID'},
                'subject_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of subject IDs to assign to department'
                }
            },
            'example': {
                'department': 1,
                'subject_ids': [1, 2, 3, 5, 7]
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=SubjectDepartmentSerializer,
            description="Department-subject mapping updated successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can update mappings"),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_subject_department(request, mapping_id):
    """Update department-subject mapping (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can update department-subject mappings'
        }, status=status.HTTP_403_FORBIDDEN)
    
    mapping = get_object_or_404(SubjectDepartment, id=mapping_id)
    
    # Use partial=True for PATCH requests
    partial = request.method == 'PATCH'
    serializer = SubjectDepartmentCreateSerializer(mapping, data=request.data, partial=partial)
    
    if serializer.is_valid():
        mapping = serializer.save()
        response_serializer = SubjectDepartmentSerializer(mapping)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Department "{mapping.department.department_name}" mapping updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Subject-Department Mapping'],
    summary="Add subjects to department",
    description="Add additional subjects to an existing department. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'subject_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of subject IDs to add to department'
                }
            },
            'required': ['subject_ids'],
            'example': {
                'subject_ids': [8, 9, 10]
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=SubjectDepartmentSerializer,
            description="Subjects added to department successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can modify mappings"),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_subjects_to_department(request, mapping_id):
    """Add subjects to existing department (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can modify department-subject mappings'
        }, status=status.HTTP_403_FORBIDDEN)
    
    mapping = get_object_or_404(SubjectDepartment, id=mapping_id)
    new_subject_ids = request.data.get('subject_ids', [])
    
    if not new_subject_ids:
        return Response({
            'success': False,
            'message': 'subject_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate subject IDs exist
    existing_subjects = Subject.objects.filter(id__in=new_subject_ids)
    existing_ids = list(existing_subjects.values_list('id', flat=True))
    
    for subject_id in new_subject_ids:
        if subject_id not in existing_ids:
            return Response({
                'success': False,
                'message': f'Subject with ID {subject_id} does not exist'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    # Add new subjects (avoid duplicates)
    current_subjects = set(mapping.subject_ids or [])
    new_subjects = set(new_subject_ids)
    updated_subjects = list(current_subjects.union(new_subjects))
    
    mapping.subject_ids = updated_subjects
    mapping.save()
    
    serializer = SubjectDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Subjects added to department "{mapping.department.department_name}" successfully'
    })


@extend_schema(
    tags=['Subject-Department Mapping'],
    summary="Remove subjects from department",
    description="Remove subjects from an existing department. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'subject_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'Array of subject IDs to remove from department'
                }
            },
            'required': ['subject_ids'],
            'example': {
                'subject_ids': [2, 3]
            }
        }
    },
    responses={
        200: OpenApiResponse(
            response=SubjectDepartmentSerializer,
            description="Subjects removed from department successfully"
        ),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can modify mappings"),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def remove_subjects_from_department(request, mapping_id):
    """Remove subjects from existing department (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can modify department-subject mappings'
        }, status=status.HTTP_403_FORBIDDEN)
    
    mapping = get_object_or_404(SubjectDepartment, id=mapping_id)
    remove_subject_ids = request.data.get('subject_ids', [])
    
    if not remove_subject_ids:
        return Response({
            'success': False,
            'message': 'subject_ids are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Remove subjects
    current_subjects = set(mapping.subject_ids or [])
    subjects_to_remove = set(remove_subject_ids)
    updated_subjects = list(current_subjects - subjects_to_remove)
    
    mapping.subject_ids = updated_subjects
    mapping.save()
    
    serializer = SubjectDepartmentSerializer(mapping)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': f'Subjects removed from department "{mapping.department.department_name}" successfully'
    })


@extend_schema(
    tags=['Subject-Department Mapping'],
    summary="Delete department-subject mapping",
    description="Delete a department-subject mapping. Only superadmin can perform this action.",
    responses={
        200: OpenApiResponse(description="Department-subject mapping deleted successfully"),
        403: OpenApiResponse(description="Only superadmin can delete mappings"),
        404: OpenApiResponse(description="Mapping not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_subject_department(request, mapping_id):
    """Delete department-subject mapping (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can delete department-subject mappings'
        }, status=status.HTTP_403_FORBIDDEN)
    
    mapping = get_object_or_404(SubjectDepartment, id=mapping_id)
    department_name = mapping.department.department_name
    subject_count = len(mapping.subject_ids or [])
    
    # Delete the mapping
    mapping.delete()
    
    return Response({
        'success': True,
        'message': f'Department "{department_name}" mapping deleted successfully',
        'note': f'This removed {subject_count} subject assignments'
    })
