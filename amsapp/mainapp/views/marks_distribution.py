from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import MarksDistribution, Department
from ..serializers.marks_distribution import (
    MarksDistributionSerializer, MarksDistributionCreateSerializer, MarksDistributionUpdateSerializer
)
from ..authentication import CustomJWTAuthentication


@extend_schema(
    operation_id='create_marks_distribution',
    tags=['Marks Distribution Management'],
    summary="Create new marks distribution",
    description="Create new marks distribution for a department with SSC, shared HSC/Diploma, main, and viva weights",
    request=MarksDistributionCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=MarksDistributionSerializer,
            description="Marks distribution created successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def create_marks_distribution(request):
    """Create new marks distribution"""
    
    serializer = MarksDistributionCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            marks_distribution = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Marks distribution created successfully',
                'data': MarksDistributionSerializer(marks_distribution).data
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating marks distribution: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='get_all_marks_distribution',
    tags=['Marks Distribution Management'],
    summary="Get all marks distribution",
    description="Retrieve all marks distribution with optional filtering by department",
    parameters=[
        OpenApiParameter(name='department_id', description='Filter by department ID', required=False, type=int),
        OpenApiParameter(name='department_name', description='Filter by department name', required=False, type=str),
    ],
    responses={
        200: OpenApiResponse(
            response=MarksDistributionSerializer(many=True),
            description="Marks distribution retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_marks_distribution(request):
    """Get all marks distribution with optional filtering"""
    
    marks_distribution = MarksDistribution.objects.select_related('department').all()
    
    # Apply filters
    department_id = request.query_params.get('department_id')
    department_name = request.query_params.get('department_name')
    
    if department_id:
        marks_distribution = marks_distribution.filter(department_id=department_id)
    
    if department_name:
        marks_distribution = marks_distribution.filter(department__department_name__icontains=department_name)
    
    # Order by department name
    marks_distribution = marks_distribution.order_by('department__department_name', '-id')
    
    serializer = MarksDistributionSerializer(marks_distribution, many=True)
    return Response({
        'success': True,
        'count': marks_distribution.count(),
        'marks_distribution': serializer.data,
        'message': f'Found {marks_distribution.count()} marks distribution records'
    })


@extend_schema(
    operation_id='get_marks_distribution_by_id',
    tags=['Marks Distribution Management'],
    summary="Get marks distribution by ID",
    description="Retrieve a specific marks distribution by its ID",
    responses={
        200: OpenApiResponse(
            response=MarksDistributionSerializer,
            description="Marks distribution retrieved successfully"
        ),
        404: OpenApiResponse(description="Marks distribution not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_marks_distribution_by_id(request, marks_distribution_id):
    """Get marks distribution by ID"""
    
    try:
        marks_distribution = MarksDistribution.objects.select_related('department').get(id=marks_distribution_id)
        serializer = MarksDistributionSerializer(marks_distribution)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Marks distribution retrieved successfully'
        })
    except MarksDistribution.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Marks distribution not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='get_marks_distribution_by_department',
    tags=['Marks Distribution Management'],
    summary="Get marks distribution by department",
    description="Retrieve all marks distribution for a specific department",
    responses={
        200: OpenApiResponse(
            response=MarksDistributionSerializer(many=True),
            description="Department marks distribution retrieved successfully"
        ),
        404: OpenApiResponse(description="Department not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_marks_distribution_by_department(request, department_id):
    """Get all marks distribution for a specific department"""
    
    try:
        # Verify department exists
        department = Department.objects.get(id=department_id)
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    marks_distribution = MarksDistribution.objects.filter(
        department=department
    ).select_related('department').order_by('-id')
    
    serializer = MarksDistributionSerializer(marks_distribution, many=True)
    return Response({
        'success': True,
        'department_info': {
            'id': department.id,
            'name': department.department_name,
            'shortname': department.department_shortname
        },
        'count': marks_distribution.count(),
        'marks_distribution': serializer.data,
        'message': f'Found {marks_distribution.count()} marks distribution records for {department.department_name}'
    })


@extend_schema(
    operation_id='update_marks_distribution',
    tags=['Marks Distribution Management'],
    summary="Update marks distribution",
    description="Update an existing marks distribution by ID",
    request=MarksDistributionUpdateSerializer,
    responses={
        200: OpenApiResponse(
            response=MarksDistributionSerializer,
            description="Marks distribution updated successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Marks distribution not found")
    }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def update_marks_distribution(request, marks_distribution_id):
    """Update marks distribution by ID"""
    
    try:
        marks_distribution = MarksDistribution.objects.get(id=marks_distribution_id)
    except MarksDistribution.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Marks distribution not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = MarksDistributionUpdateSerializer(marks_distribution, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            updated_distribution = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Marks distribution updated successfully',
                'data': MarksDistributionSerializer(updated_distribution).data
            })
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error updating marks distribution: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='delete_marks_distribution',
    tags=['Marks Distribution Management'],
    summary="Delete marks distribution",
    description="Delete an existing marks distribution by ID",
    responses={
        200: OpenApiResponse(description="Marks distribution deleted successfully"),
        404: OpenApiResponse(description="Marks distribution not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_marks_distribution(request, marks_distribution_id):
    """Delete marks distribution by ID"""
    
    try:
        marks_distribution = MarksDistribution.objects.get(id=marks_distribution_id)
        
        distribution_info = {
            'id': marks_distribution.id,
            'department_name': marks_distribution.department.department_name,
            'ssc': marks_distribution.ssc,
            'hsc': marks_distribution.hsc,
            'diploma': marks_distribution.diploma,
            'main_marks': marks_distribution.main_marks,
            'viva_marks': marks_distribution.viva_marks
        }
        
        marks_distribution.delete()
        
        return Response({
            'success': True,
            'message': 'Marks distribution deleted successfully',
            'deleted_distribution': distribution_info
        })
        
    except MarksDistribution.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Marks distribution not found'
        }, status=status.HTTP_404_NOT_FOUND)
