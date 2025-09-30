from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models import Department
from ..serializers import DepartmentSerializer


@extend_schema(
    tags=['Departments'],
    summary="Get all departments",
    description="Retrieve all departments in the system.",
    responses={
        200: OpenApiResponse(
            response=DepartmentSerializer(many=True),
            description="List of all departments"
        )
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
    tags=['Departments'],
    summary="Create a new department",
    description="Create a new department. Only superadmin can perform this action.",
    request=DepartmentSerializer,
    responses={
        201: OpenApiResponse(
            response=DepartmentSerializer,
            description="Department created successfully"
        ),
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
    
    serializer = DepartmentSerializer(data=request.data)
    if serializer.is_valid():
        department = serializer.save()
        return Response({
            'success': True,
            'data': serializer.data,
            'message': f'Department "{department.department_name}" created successfully'
        }, status=status.HTTP_201_CREATED)
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Departments'],
    summary="Get department by ID",
    description="Retrieve a specific department by its ID.",
    responses={
        200: OpenApiResponse(
            response=DepartmentSerializer,
            description="Department details"
        ),
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
    tags=['Departments'],
    summary="Update department",
    description="Update department details. Only superadmin can perform this action.",
    request=DepartmentSerializer,
    responses={
        200: OpenApiResponse(
            response=DepartmentSerializer,
            description="Department updated successfully"
        ),
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
    serializer = DepartmentSerializer(department, data=request.data, partial=partial)
    
    if serializer.is_valid():
        department = serializer.save()
        return Response({
            'success': True,
            'data': serializer.data,
            'message': f'Department "{department.department_name}" updated successfully'
        })
    else:
        return Response({
            'success': False,
            'message': 'Invalid data provided',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
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