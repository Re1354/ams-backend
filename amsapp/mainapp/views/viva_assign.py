from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models.viva_assign import VivaAssignment
from ..serializers.viva_assign import (
    VivaAssignmentSerializer, VivaAssignmentCreateSerializer, VivaAssignmentBulkCreateSerializer
)
from ..authentication import CustomJWTAuthentication

@extend_schema(
    operation_id='create_viva_assignment',
    tags=['Viva Assignment Management'],
    summary="Create viva assignment(s)",
    description="Create a single or multiple viva assignments. For bulk, send a list under 'assignments' key.",
    request=VivaAssignmentBulkCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=VivaAssignmentSerializer(many=True),
            description="Viva assignment(s) created successfully"
        ),
        400: OpenApiResponse(description="Invalid request data or duplicate assignment")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def create_viva_assignment(request):
    """Create single or bulk viva assignments"""
    is_bulk = isinstance(request.data.get('assignments'), list)
    if is_bulk:
        serializer = VivaAssignmentBulkCreateSerializer(data=request.data)
    else:
        serializer = VivaAssignmentCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    try:
        with transaction.atomic():
            if is_bulk:
                assignments = []
                for item in serializer.validated_data['assignments']:
                    assignment = VivaAssignment.objects.create(**item)
                    assignments.append(assignment)
                return Response({
                    'success': True,
                    'message': f'{len(assignments)} viva assignments created successfully',
                    'data': VivaAssignmentSerializer(assignments, many=True).data
                }, status=status.HTTP_201_CREATED)
            else:
                assignment = serializer.save()
                return Response({
                    'success': True,
                    'message': 'Viva assignment created successfully',
                    'data': VivaAssignmentSerializer(assignment).data
                }, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating viva assignment(s): {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    operation_id='get_all_viva_assignments',
    tags=['Viva Assignment Management'],
    summary="Get all viva assignments",
    description="Retrieve all viva assignments with optional filtering by exam, student, or teacher.",
    parameters=[
        OpenApiParameter(name='exam_id', description='Filter by exam ID', required=False, type=int),
        OpenApiParameter(name='student_id', description='Filter by student ID', required=False, type=int),
        OpenApiParameter(name='teacher_id', description='Filter by teacher ID', required=False, type=int),
    ],
    responses={
        200: OpenApiResponse(
            response=VivaAssignmentSerializer(many=True),
            description="Viva assignments retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_viva_assignments(request):
    """Get all viva assignments with optional filtering"""
    viva_assignments = VivaAssignment.objects.select_related('student', 'teacher', 'exam').all()
    exam_id = request.query_params.get('exam_id')
    student_id = request.query_params.get('student_id')
    teacher_id = request.query_params.get('teacher_id')
    if exam_id:
        viva_assignments = viva_assignments.filter(exam_id=exam_id)
    if student_id:
        viva_assignments = viva_assignments.filter(student_id=student_id)
    if teacher_id:
        viva_assignments = viva_assignments.filter(teacher_id=teacher_id)
    viva_assignments = viva_assignments.order_by('-created_at')
    serializer = VivaAssignmentSerializer(viva_assignments, many=True)
    return Response({
        'success': True,
        'count': viva_assignments.count(),
        'assignments': serializer.data,
        'message': f'Found {viva_assignments.count()} viva assignments'
    })

@extend_schema(
    operation_id='get_viva_assignments_by_teacher',
    tags=['Viva Assignment Management'],
    summary="Get all viva assignments for a specific teacher",
    description="Retrieve all students assigned to a specific teacher for viva examination",
    responses={
        200: OpenApiResponse(
            response=VivaAssignmentSerializer(many=True),
            description="Viva assignments retrieved successfully"
        ),
        404: OpenApiResponse(description="Teacher not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_viva_assignments_by_teacher(request, teacher_id):
    """Get all viva assignments for a specific teacher"""
    from ..models import User
    
    # Check if teacher exists
    try:
        teacher = User.objects.get(id=teacher_id)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Teacher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Get all viva assignments for this teacher
    viva_assignments = VivaAssignment.objects.filter(
        teacher_id=teacher_id
    ).select_related('student', 'teacher', 'exam').order_by('-created_at')
    
    serializer = VivaAssignmentSerializer(viva_assignments, many=True)
    
    return Response({
        'success': True,
        'teacher': {
            'id': teacher.id,
            'username': teacher.username,
            'email': teacher.email
        },
        'count': viva_assignments.count(),
        'assignments': serializer.data,
        'message': f'Found {viva_assignments.count()} viva assignments for teacher {teacher.username}'
    })


@extend_schema(
    operation_id='delete_viva_assignment',
    tags=['Viva Assignment Management'],
    summary="Delete viva assignment",
    description="Delete a viva assignment by ID",
    responses={
        200: OpenApiResponse(description="Viva assignment deleted successfully"),
        404: OpenApiResponse(description="Viva assignment not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_viva_assignment(request, assignment_id):
    """Delete viva assignment by ID"""
    try:
        assignment = VivaAssignment.objects.get(id=assignment_id)
        assignment_info = {
            'id': assignment.id,
            'student': assignment.student.username,
            'teacher': assignment.teacher.username,
            'exam': assignment.exam.id
        }
        assignment.delete()
        return Response({
            'success': True,
            'message': 'Viva assignment deleted successfully',
            'deleted_assignment': assignment_info
        })
    except VivaAssignment.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Viva assignment not found'
        }, status=status.HTTP_404_NOT_FOUND)
