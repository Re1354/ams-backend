from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
import logging
import threading

from django.db import close_old_connections, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import AdmissionConfiguration, DepartmentThreshold, Department
from ..serializers.department_threshold import (
    DepartmentThresholdSerializer, 
    BulkThresholdMappingSerializer,
    ThresholdMappingResponseSerializer
)
from ..authentication import CustomJWTAuthentication
from ..services.admission_calculator import calculate_semester_admission_results

logger = logging.getLogger(__name__)


def queue_threshold_recalculation(department_ids, semester):
    def run_recalculation():
        close_old_connections()
        try:
            departments = Department.objects.filter(id__in=department_ids)
            for department in departments:
                calculate_semester_admission_results(department=department, semester=semester)
        except Exception:
            logger.exception("Failed to recalculate admission results after threshold update")
        finally:
            close_old_connections()

    thread = threading.Thread(
        target=run_recalculation,
        name=f"threshold-recalculation-{semester}",
        daemon=True,
    )
    thread.start()


@extend_schema(
    operation_id='set_threshold_mapping',
    tags=['Admission Management'],
    summary="Set department threshold mappings for a semester",
    description="Bulk create or update department threshold mappings for a specific semester. "
                "All exams within this semester will use these thresholds and seat limits.",
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
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def set_threshold_mapping(request):
    """
    Set department threshold mappings for a semester.
    
    Request body:
    {
        "semester": "Fall 2025",
        "mappings": [
            {"department_id": 2, "threshold": 60.0, "seat_limit": 5},
            {"department_id": 3, "threshold": 75.0, "seat_limit": 8}
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
    
    semester = serializer.validated_data['semester']
    mappings = serializer.validated_data['mappings']
    
    created_count = 0
    updated_count = 0
    created_thresholds = []
    updated_departments = []
    
    with transaction.atomic():
        for mapping in mappings:
            department_id = mapping['department_id']
            threshold_value = mapping['threshold']
            dept_seat_limit = mapping['seat_limit']
            
            try:
                department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                return Response({
                    'success': False,
                    'message': f'Department with ID {department_id} not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Create or update threshold
            threshold, created = DepartmentThreshold.objects.update_or_create(
                semester=semester,
                department=department,
                defaults={
                    'min_threshold_mark': threshold_value,
                    'seat_limit': dept_seat_limit
                }
            )

            configuration, _ = AdmissionConfiguration.objects.get_or_create(
                department=department,
                semester=semester,
                defaults={
                    'seat_limit': dept_seat_limit,
                    'threshold': threshold_value,
                }
            )
            config_updates = []
            if configuration.seat_limit != dept_seat_limit:
                configuration.seat_limit = dept_seat_limit
                config_updates.append('seat_limit')
            if configuration.threshold != threshold_value:
                configuration.threshold = threshold_value
                config_updates.append('threshold')
            if config_updates:
                configuration.save(update_fields=config_updates + ['updated_at'])
            
            created_thresholds.append(threshold)
            if created:
                created_count += 1
            else:
                updated_count += 1

            updated_departments.append(department)
    
    response_status = status.HTTP_201_CREATED if created_count > 0 else status.HTTP_200_OK

    recalculation_department_ids = list({dept.id for dept in updated_departments})
    if recalculation_department_ids:
        queue_threshold_recalculation(recalculation_department_ids, semester)
    
    return Response({
        'success': True,
        'message': f'Threshold mappings processed successfully for semester "{semester}". '
                  f'Created: {created_count}, Updated: {updated_count}',
        'created_count': created_count,
        'updated_count': updated_count,
        'recalculation_queued': bool(recalculation_department_ids),
        'data': DepartmentThresholdSerializer(created_thresholds, many=True).data
    }, status=response_status)


@extend_schema(
    operation_id='get_threshold_mapping',
    tags=['Admission Management'],
    summary="Get department threshold mappings",
    description="Retrieve department threshold mappings for a specific semester or all semesters",
    parameters=[
        OpenApiParameter(
            name='semester',
            description='Filter by semester (e.g., "Fall 2025")',
            required=False,
            type=str
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
    """Get department threshold mappings with optional filtering by semester or department"""
    
    thresholds = DepartmentThreshold.objects.select_related('department').all()
    
    # Apply filters
    semester = request.query_params.get('semester')
    department_id = request.query_params.get('department_id')
    
    if semester:
        thresholds = thresholds.filter(semester=semester)
    
    if department_id:
        thresholds = thresholds.filter(department_id=department_id)
    
    # Order by semester (newest first) and department name
    thresholds = thresholds.order_by('-semester', 'department__department_name')
    
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
            'department'
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
            'semester': threshold.semester,
            'department': threshold.department.department_name,
            'threshold': threshold.min_threshold_mark,
            'seat_limit': threshold.seat_limit
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
