from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import AdmissionResult, Exam, Students, Department
from ..serializers.admission_result import (
    AdmissionResultSerializer,
    CalculateAdmissionResultsSerializer,
    CalculateResultsResponseSerializer,
    AdmissionResultFilterSerializer
)
from ..services.admission_calculator import calculate_admission_results, recalculate_single_student_result
from ..authentication import CustomJWTAuthentication


class AdmissionResultsPagination(PageNumberPagination):
    """Custom pagination for admission results"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@extend_schema(
    operation_id='calculate_admission_results',
    tags=['Admission Management'],
    summary="Calculate admission results for an exam",
    description="Triggers calculation of admission results for all students who took the specified exam. "
                "This will compute MCQ + Viva marks and determine selection status based on department thresholds.",
    request=CalculateAdmissionResultsSerializer,
    responses={
        200: OpenApiResponse(
            response=CalculateResultsResponseSerializer,
            description="Results calculated successfully"
        ),
        400: OpenApiResponse(description="Invalid request data or missing thresholds"),
        404: OpenApiResponse(description="Exam not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def calculate_results(request):
    """
    Calculate admission results for an exam.
    
    Request body:
    {
        "exam_id": 1
    }
    """
    serializer = CalculateAdmissionResultsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exam_id = serializer.validated_data['exam_id']
    
    # Call the calculation service
    result = calculate_admission_results(exam_id)
    
    if not result['success']:
        return Response({
            'success': False,
            'message': 'Failed to calculate results',
            'errors': result.get('errors', [])
        }, status=status.HTTP_400_BAD_REQUEST)
    
    response_data = {
        'success': True,
        'message': f"Results calculated successfully. Processed {result['processed_count']} students.",
        'processed_count': result['processed_count'],
        'selected_count': result['selected_count'],
        'not_selected_count': result['not_selected_count'],
        'exam_id': exam_id
    }
    
    # Include warnings if there were any errors
    if result.get('errors'):
        response_data['warnings'] = result['errors']
    
    return Response(response_data)


@extend_schema(
    operation_id='get_admission_results',
    tags=['Admission Management'],
    summary="Get admission results",
    description="Retrieve paginated list of admission results with optional filtering",
    parameters=[
        OpenApiParameter(name='exam_id', description='Filter by exam ID', required=False, type=int),
        OpenApiParameter(name='department_id', description='Filter by department ID', required=False, type=int),
        OpenApiParameter(name='student_id', description='Filter by student ID', required=False, type=int),
        OpenApiParameter(name='is_selected', description='Filter by selection status (true/false)', required=False, type=bool),
        OpenApiParameter(name='status', description='Filter by publication status (PENDING/PUBLISHED/CANCELLED)', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Number of results per page (max 100)', required=False, type=int),
    ],
    responses={
        200: OpenApiResponse(
            response=AdmissionResultSerializer(many=True),
            description="Admission results retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_admission_results(request):
    """Get admission results with filtering and pagination"""
    
    results = AdmissionResult.objects.select_related(
        'exam', 'student', 'department'
    ).all()
    
    # Apply filters
    exam_id = request.query_params.get('exam_id')
    department_id = request.query_params.get('department_id')
    student_id = request.query_params.get('student_id')
    is_selected = request.query_params.get('is_selected')
    result_status = request.query_params.get('status')
    
    if exam_id:
        results = results.filter(exam_id=exam_id)
    
    if department_id:
        results = results.filter(department_id=department_id)
    
    if student_id:
        results = results.filter(student_id=student_id)
    
    if is_selected is not None:
        # Convert string to boolean
        is_selected_bool = is_selected.lower() in ['true', '1', 'yes']
        results = results.filter(is_selected=is_selected_bool)
    
    if result_status:
        results = results.filter(status__iexact=result_status)
    
    # Order by total marks (highest first)
    results = results.order_by('-total_marks', '-created_at')
    
    # Apply pagination
    paginator = AdmissionResultsPagination()
    page = paginator.paginate_queryset(results, request)
    
    if page is not None:
        serializer = AdmissionResultSerializer(page, many=True)
        response = paginator.get_paginated_response(serializer.data)
        
        # Add custom metadata
        response.data['success'] = True
        response.data['filters_applied'] = {
            'exam_id': exam_id,
            'department_id': department_id,
            'student_id': student_id,
            'is_selected': is_selected,
            'status': result_status
        }
        
        return response
    
    # If pagination is not applied
    serializer = AdmissionResultSerializer(results, many=True)
    return Response({
        'success': True,
        'count': results.count(),
        'results': serializer.data
    })


@extend_schema(
    operation_id='get_admission_result_by_id',
    tags=['Admission Management'],
    summary="Get specific admission result by ID",
    description="Retrieve a specific admission result by its ID",
    responses={
        200: OpenApiResponse(
            response=AdmissionResultSerializer,
            description="Admission result retrieved successfully"
        ),
        404: OpenApiResponse(description="Admission result not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_admission_result_by_id(request, result_id):
    """Get specific admission result by ID"""
    
    try:
        result = AdmissionResult.objects.select_related(
            'exam', 'student', 'department'
        ).get(id=result_id)
    except AdmissionResult.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Admission result not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = AdmissionResultSerializer(result)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Admission result retrieved successfully'
    })


@extend_schema(
    operation_id='get_student_admission_result',
    tags=['Admission Management'],
    summary="Get admission result for a specific student in an exam",
    description="Retrieve the admission result for a specific student in a specific exam",
    responses={
        200: OpenApiResponse(
            response=AdmissionResultSerializer,
            description="Student admission result retrieved successfully"
        ),
        404: OpenApiResponse(description="Result not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_student_admission_result(request, exam_id, student_id):
    """Get admission result for a specific student in an exam"""
    
    try:
        result = AdmissionResult.objects.select_related(
            'exam', 'student', 'department'
        ).get(exam_id=exam_id, student_id=student_id)
    except AdmissionResult.DoesNotExist:
        return Response({
            'success': False,
            'message': f'No admission result found for student {student_id} in exam {exam_id}'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = AdmissionResultSerializer(result)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Student admission result retrieved successfully'
    })


@extend_schema(
    operation_id='publish_admission_results',
    tags=['Admission Management'],
    summary="Publish admission results",
    description="Change status of admission results to PUBLISHED for a specific exam",
    request=CalculateAdmissionResultsSerializer,
    responses={
        200: OpenApiResponse(description="Results published successfully"),
        404: OpenApiResponse(description="Exam not found or no results to publish")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def publish_admission_results(request):
    """
    Publish admission results for an exam.
    Changes status from PENDING to PUBLISHED.
    
    Request body:
    {
        "exam_id": 1
    }
    """
    serializer = CalculateAdmissionResultsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exam_id = serializer.validated_data['exam_id']
    
    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        return Response({
            'success': False,
            'message': f'Exam with ID {exam_id} not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Update all PENDING results to PUBLISHED
    with transaction.atomic():
        updated_count = AdmissionResult.objects.filter(
            exam=exam,
            status='PENDING'
        ).update(status='PUBLISHED')
    
    if updated_count == 0:
        return Response({
            'success': False,
            'message': 'No pending results found for this exam'
        }, status=status.HTTP_404_NOT_FOUND)
    
    return Response({
        'success': True,
        'message': f'Published {updated_count} admission results for exam {exam_id}',
        'published_count': updated_count,
        'exam_id': exam_id
    })


@extend_schema(
    operation_id='recalculate_student_result',
    tags=['Admission Management'],
    summary="Recalculate result for a single student",
    description="Recalculate admission result for a specific student in a specific exam",
    request=None,
    responses={
        200: OpenApiResponse(
            response=AdmissionResultSerializer,
            description="Student result recalculated successfully"
        ),
        400: OpenApiResponse(description="Calculation failed"),
        404: OpenApiResponse(description="Student or exam not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def recalculate_student_result(request, exam_id, student_id):
    """Recalculate admission result for a single student"""
    
    result = recalculate_single_student_result(exam_id, student_id)
    
    if not result['success']:
        return Response({
            'success': False,
            'message': result.get('error', 'Failed to recalculate result')
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Fetch the updated result
    try:
        admission_result = AdmissionResult.objects.select_related(
            'exam', 'student', 'department'
        ).get(exam_id=exam_id, student_id=student_id)
        
        serializer = AdmissionResultSerializer(admission_result)
        return Response({
            'success': True,
            'message': f"Result {result['action']} successfully for student {result['student']}",
            'data': serializer.data
        })
    except AdmissionResult.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Failed to retrieve recalculated result'
        }, status=status.HTTP_404_NOT_FOUND)
