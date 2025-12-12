from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import DepartmentThreshold, Exam, Department
from ..serializers.department_threshold import (
    DepartmentThresholdSerializer, 
    BulkThresholdMappingSerializer,
    ThresholdMappingResponseSerializer
)
from ..authentication import CustomJWTAuthentication


@extend_schema(
    operation_id='set_threshold_mapping',
    tags=['Admission Management'],
    summary="Set department threshold mappings for an exam",
    description="Bulk create or update department threshold mappings for a specific exam. "
                "This sets the minimum marks required for admission to each department.",
    request=BulkThresholdMappingSerializer,
    responses={
        200: OpenApiResponse(
            response=ThresholdMappingResponseSerializer,
            description="Threshold mappings updated successfully"
        ),
        201: OpenApiResponse(
            response=ThresholdMappingResponseSerializer,
            description="Threshold mappings created successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Exam or department not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def set_threshold_mapping(request):
    """
    Set department threshold mappings for an exam.
    
    Request body:
    {
        "exam_id": 1,
        "mappings": [
            {"department_id": 2, "threshold": 60.0},
            {"department_id": 3, "threshold": 75.0}
        ]
    }
    """
    serializer = BulkThresholdMappingSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exam_id = serializer.validated_data['exam_id']
    mappings = serializer.validated_data['mappings']
    
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return Response({
            'success': False,
            'message': f'Exam with ID {exam_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    created_count = 0
    updated_count = 0
    created_thresholds = []
    
    with transaction.atomic():
        for mapping in mappings:
            department_id = mapping['department_id']
            threshold_value = mapping['threshold']
            
            try:
                department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return Response({
                    'success': False,
                    'message': f'Department with ID {department_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Validate threshold doesn't exceed exam total marks
            if threshold_value > exam.total_marks:
                return Response({
                    'success': False,
                    'message': f'Threshold ({threshold_value}) for department {department.department_name} '
                              f'cannot exceed exam total marks ({exam.total_marks})'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create or update threshold
            threshold, created = DepartmentThreshold.objects.update_or_create(
                exam=exam,
                department=department,
                defaults={'min_threshold_mark': threshold_value}
            )
            
            created_thresholds.append(threshold)
            if created:
                created_count += 1
            else:
                updated_count += 1
    
    response_status = status.HTTP_201_CREATED if created_count > 0 else status.HTTP_200_OK
    
    return Response({
        'success': True,
        'message': f'Threshold mappings processed successfully. '
                  f'Created: {created_count}, Updated: {updated_count}',
        'created_count': created_count,
        'updated_count': updated_count,
        'data': DepartmentThresholdSerializer(created_thresholds, many=True).data
    }, status=response_status)


@extend_schema(
    operation_id='get_threshold_mapping',
    tags=['Admission Management'],
    summary="Get department threshold mappings",
    description="Retrieve department threshold mappings for a specific exam or all exams",
    parameters=[
        OpenApiParameter(
            name='exam_id',
            description='Filter by exam ID',
            required=False,
            type=int
        ),
        OpenApiParameter(
            name='department_id',
            description='Filter by department ID',
            required=False,
            type=int
        ),
    ],
    responses={
        200: OpenApiResponse(
            response=DepartmentThresholdSerializer(many=True),
            description="Threshold mappings retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_threshold_mapping(request):
    """Get department threshold mappings with optional filtering"""
    
    thresholds = DepartmentThreshold.objects.select_related('exam', 'department').all()
    
    # Apply filters
    exam_id = request.query_params.get('exam_id')
    department_id = request.query_params.get('department_id')
    
    if exam_id:
        thresholds = thresholds.filter(exam_id=exam_id)
    
    if department_id:
        thresholds = thresholds.filter(department_id=department_id)
    
    # Order by exam and department
    thresholds = thresholds.order_by('-exam__created_at', 'department__department_name')
    
    serializer = DepartmentThresholdSerializer(thresholds, many=True)
    
    return Response({
        'success': True,
        'count': thresholds.count(),
        'thresholds': serializer.data,
        'message': f'Found {thresholds.count()} threshold mappings'
    })


@extend_schema(
    operation_id='get_threshold_by_id',
    tags=['Admission Management'],
    summary="Get specific threshold mapping by ID",
    description="Retrieve a specific department threshold mapping by its ID",
    responses={
        200: OpenApiResponse(
            response=DepartmentThresholdSerializer,
            description="Threshold mapping retrieved successfully"
        ),
        404: OpenApiResponse(description="Threshold mapping not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_threshold_by_id(request, threshold_id):
    """Get specific threshold mapping by ID"""
    
    try:
        threshold = DepartmentThreshold.objects.select_related(
            'exam', 'department'
        ).get(id=threshold_id)
    except DepartmentThreshold.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Threshold mapping not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = DepartmentThresholdSerializer(threshold)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Threshold mapping retrieved successfully'
    })


@extend_schema(
    operation_id='delete_threshold_mapping',
    tags=['Admission Management'],
    summary="Delete threshold mapping",
    description="Delete a specific department threshold mapping by ID",
    responses={
        200: OpenApiResponse(description="Threshold mapping deleted successfully"),
        404: OpenApiResponse(description="Threshold mapping not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_threshold_mapping(request, threshold_id):
    """Delete specific threshold mapping"""
    
    try:
        threshold = DepartmentThreshold.objects.get(id=threshold_id)
        threshold_info = {
            'id': threshold.id,
            'exam_id': threshold.exam.id,
            'department': threshold.department.department_name,
            'threshold': threshold.min_threshold_mark
        }
        threshold.delete()
        
        return Response({
            'success': True,
            'message': 'Threshold mapping deleted successfully',
            'deleted_threshold': threshold_info
        })
    except DepartmentThreshold.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Threshold mapping not found'
        }, status=status.HTTP_404_NOT_FOUND)
