from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import Students
from ..serializers.student import StudentsSerializer, StudentCreateSerializer, StudentUpdateSerializer
from ..authentication import CustomJWTAuthentication
from ..utils import normalize_semester_filter


@extend_schema(
    operation_id='get_all_students',
    tags=['Student Management'],
    summary="Get all students",
    description="Retrieve all registered students with SSC, HSC, and Diploma marks",
    parameters=[
        OpenApiParameter(name='department_shortname', description='Filter by department shortname', required=False, type=str),
        OpenApiParameter(name='registration_semester', description='Filter by student registration semester', required=False, type=str),
        OpenApiParameter(name='username', description='Filter by username', required=False, type=str),
    ],
    responses={
        200: OpenApiResponse(
            response=StudentsSerializer(many=True),
            description="Students retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_students(request):
    """Get all students with optional filtering"""
    
    students = Students.objects.all()
    
    # Apply filters
    department_filter = request.query_params.get('department_shortname')
    registration_semester_filter = request.query_params.get('registration_semester')
    username_filter = request.query_params.get('username')
    
    if department_filter:
        students = students.filter(department_shortname__icontains=department_filter)

    if registration_semester_filter:
        students = students.filter(
            registration_semester__icontains=normalize_semester_filter(
                registration_semester_filter
            )
        )
    
    if username_filter:
        students = students.filter(username__icontains=username_filter)
    
    # Order by creation date
    students = students.order_by('-created_at')
    
    serializer = StudentsSerializer(students, many=True)
    return Response({
        'success': True,
        'count': students.count(),
        'students': serializer.data,
        'message': f'Found {students.count()} students'
    })


@extend_schema(
    operation_id='create_student',
    tags=['Student Management'],
    summary="Create new student",
    description="Create a new student with SSC, HSC, and Diploma marks",
    request=StudentCreateSerializer,
    responses={
        201: OpenApiResponse(
            response=StudentsSerializer,
            description="Student created successfully"
        ),
        400: OpenApiResponse(description="Invalid request data")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def create_student(request):
    """Create new student"""
    
    serializer = StudentCreateSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            student = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Student created successfully',
                'data': StudentsSerializer(student).data
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating student: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='get_student_by_id',
    tags=['Student Management'],
    summary="Get student by ID",
    description="Retrieve a specific student by their ID",
    responses={
        200: OpenApiResponse(
            response=StudentsSerializer,
            description="Student retrieved successfully"
        ),
        404: OpenApiResponse(description="Student not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_student_by_id(request, student_id):
    """Get student by ID"""
    
    try:
        student = Students.objects.get(id=student_id)
        serializer = StudentsSerializer(student)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Student retrieved successfully'
        })
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='update_student',
    tags=['Student Management'],
    summary="Update student",
    description="Update an existing student's information including SSC, HSC, and Diploma marks",
    request=StudentUpdateSerializer,
    responses={
        200: OpenApiResponse(
            response=StudentsSerializer,
            description="Student updated successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Student not found")
    }
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def update_student(request, student_id):
    """Update student by ID"""
    
    try:
        student = Students.objects.get(id=student_id)
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    serializer = StudentUpdateSerializer(student, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            updated_student = serializer.save()
            
            return Response({
                'success': True,
                'message': 'Student updated successfully',
                'data': StudentsSerializer(updated_student).data
            })
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error updating student: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='delete_student',
    tags=['Student Management'],
    summary="Delete student",
    description="Delete an existing student by ID",
    responses={
        200: OpenApiResponse(description="Student deleted successfully"),
        404: OpenApiResponse(description="Student not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_student(request, student_id):
    """Delete student by ID"""
    
    try:
        student = Students.objects.get(id=student_id)
        
        student_info = {
            'id': student.id,
            'username': student.username,
            'full_name': student.full_name,
            'f_id': student.f_id,
            'department_shortname': student.department_shortname,
            'registration_semester': student.registration_semester
        }
        
        student.delete()
        
        return Response({
            'success': True,
            'message': 'Student deleted successfully',
            'deleted_student': student_info
        })
        
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)


