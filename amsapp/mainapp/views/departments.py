from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models import Department
from ..serializers.departments import DepartmentSerializer, DepartmentCreateSerializer, DepartmentDetailSerializer


@extend_schema(
    operation_id='get_all_departments',
    tags=['Departments'],
    summary="Get all departments",
    description="Retrieve all departments in the system with their names and shortnames.",
    responses={
        200: {
            'description': 'Departments retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': [
                            {
                                'id': 1,
                                'department_name': 'Computer Science and Engineering',
                                'department_shortname': 'CSE'
                            },
                            {
                                'id': 2,
                                'department_name': 'Electrical and Electronic Engineering',
                                'department_shortname': 'EEE'
                            }
                        ],
                        'message': 'Departments retrieved successfully'
                    }
                }
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_departments(request):
    """Get all departments"""
    departments = Department.objects.all().order_by('department_name')
    serializer = DepartmentSerializer(departments, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Departments retrieved successfully'
    })


@extend_schema(
    operation_id='create_department',
    tags=['Departments'],
    summary="Create a new department",
    description="Create a new department with name and shortname. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'department_name': {
                    'type': 'string',
                    'description': 'Full name of the department',
                    'example': 'Computer Science and Engineering'
                },
                'department_shortname': {
                    'type': 'string',
                    'description': 'Short name/abbreviation of the department',
                    'example': 'CSE'
                }
            },
            'required': ['department_name', 'department_shortname']
        }
    },
    responses={
        201: {
            'description': 'Department created successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'department_name': 'Computer Science and Engineering',
                            'department_shortname': 'CSE'
                        },
                        'message': 'Department "Computer Science and Engineering" created successfully'
                    }
                }
            }
        },
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can create departments")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_department(request):
    """Create a new department (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can create departments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    serializer = DepartmentCreateSerializer(data=request.data)
    if serializer.is_valid():
        department = serializer.save()
        response_serializer = DepartmentSerializer(department)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Department "{department.department_name}" created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_department_by_id',
    tags=['Departments'],
    summary="Get department by ID",
    description="Retrieve a specific department by its ID with name and shortname.",
    responses={
        200: {
            'description': 'Department retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'department_name': 'Computer Science and Engineering',
                            'department_shortname': 'CSE'
                        },
                        'message': 'Department retrieved successfully'
                    }
                }
            }
        },
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_department_by_id(request, department_id):
    """Get department by ID"""
    department = get_object_or_404(Department, id=department_id)
    serializer = DepartmentSerializer(department)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Department retrieved successfully'
    })


@extend_schema(
    operation_id='update_department',
    tags=['Departments'],
    summary="Update department",
    description="Update department name and/or shortname. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'department_name': {
                    'type': 'string',
                    'description': 'Full name of the department',
                    'example': 'Computer Science and Engineering'
                },
                'department_shortname': {
                    'type': 'string',
                    'description': 'Short name/abbreviation of the department',
                    'example': 'CSE'
                }
            }
        }
    },
    responses={
        200: {
            'description': 'Department updated successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'data': {
                            'id': 1,
                            'department_name': 'Computer Science and Engineering',
                            'department_shortname': 'CSE'
                        },
                        'message': 'Department "Computer Science and Engineering" updated successfully'
                    }
                }
            }
        },
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can update departments"),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_department(request, department_id):
    """Update department (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can update departments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    department = get_object_or_404(Department, id=department_id)
    
    # Use partial=True for PATCH requests
    partial = request.method == 'PATCH'
    serializer = DepartmentCreateSerializer(department, data=request.data, partial=partial)
    
    if serializer.is_valid():
        department = serializer.save()
        response_serializer = DepartmentSerializer(department)
        return Response({
            'success': True,
            'data': response_serializer.data,
            'message': f'Department "{department.department_name}" updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='delete_department',
    tags=['Departments'],
    summary="Delete department",
    description="Delete a department. Only superadmin can perform this action. Warning: This will affect all users assigned to this department.",
    responses={
        200: OpenApiResponse(description="Department deleted successfully"),
        403: OpenApiResponse(description="Only superadmin can delete departments"),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_department(request, department_id):
    """Delete department (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can delete departments'
        }, status=status.HTTP_403_FORBIDDEN)
    
    department = get_object_or_404(Department, id=department_id)
    department_name = department.department_name
    
    # Get count of users that will be affected
    users_count = department.users.count()
    
    # Delete the department
    department.delete()
    
    return Response({
        'success': True,
        'message': f'Department "{department_name}" deleted successfully',
        'note': f'This affected {users_count} users' if users_count > 0 else 'No users were affected'
    })