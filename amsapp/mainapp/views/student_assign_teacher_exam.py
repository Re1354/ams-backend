from rest_framework import status, generics
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import StudentAssignTeacherExam, Students, User, Exam, ExamSchedule
from ..serializers.student_assign_teacher_exam import (
    StudentAssignTeacherExamSerializer, 
    StudentAssignBulkSerializer, 
    StudentAssignSingleSerializer
)
from ..serializers.exam import ExamScheduleSerializer
from ..authentication import CustomJWTAuthentication
from ..utils import normalize_semester_filter, paginate_queryset


def apply_assignment_filters(assignments, request):
    search = request.query_params.get('search')
    teacher_id = request.query_params.get('teacher_id')
    exam_id = request.query_params.get('exam_id')
    schedule_id = request.query_params.get('schedule_id')
    department_filter = request.query_params.get('department')
    semester_filter = request.query_params.get('semester')
    registration_semester_filter = request.query_params.get('registration_semester')
    date_filter = request.query_params.get('date_filter')

    if search:
        normalized_search_semester = normalize_semester_filter(search)
        search_query = (
            Q(student__username__icontains=search)
            | Q(student__full_name__icontains=search)
            | Q(student__f_id__icontains=search)
            | Q(student__email__icontains=search)
            | Q(student__department_shortname__icontains=search)
            | Q(student__registration_semester__icontains=normalized_search_semester)
            | Q(teacher__username__icontains=search)
            | Q(teacher__email__icontains=search)
            | Q(exam__department__icontains=search)
            | Q(exam__semester__icontains=normalized_search_semester)
        )
        if str(search).isdigit():
            search_query |= Q(exam_id=int(search)) | Q(schedule_id=int(search))
        assignments = assignments.filter(search_query)

    if teacher_id:
        assignments = assignments.filter(teacher_id=teacher_id)
    if exam_id:
        assignments = assignments.filter(exam_id=exam_id)
    if schedule_id:
        assignments = assignments.filter(schedule_id=schedule_id)
    if department_filter:
        assignments = assignments.filter(exam__department__icontains=department_filter)
    if semester_filter:
        assignments = assignments.filter(exam__semester__icontains=normalize_semester_filter(semester_filter))
    if registration_semester_filter:
        assignments = assignments.filter(
            student__registration_semester__icontains=normalize_semester_filter(
                registration_semester_filter
            )
        )
    if date_filter == 'today':
        assignments = assignments.filter(created_at__date=timezone.localdate())

    return assignments


def build_assignment_filter_options(assignments):
    return {
        'departments': list(
            assignments.exclude(exam__department__isnull=True)
            .exclude(exam__department='')
            .order_by('exam__department')
            .values_list('exam__department', flat=True)
            .distinct()
        ),
        'semesters': list(
            assignments.exclude(exam__semester__isnull=True)
            .exclude(exam__semester='')
            .order_by('exam__semester')
            .values_list('exam__semester', flat=True)
            .distinct()
        ),
        'registration_semesters': list(
            assignments.exclude(student__registration_semester__isnull=True)
            .exclude(student__registration_semester='')
            .order_by('student__registration_semester')
            .values_list('student__registration_semester', flat=True)
            .distinct()
        ),
    }


@extend_schema(
    operation_id='assign_students_bulk',
    tags=['Student Assignment'],
    summary="Bulk assign students to teacher and exam",
    description="Assign multiple students to a teacher and exam in one request. The exam_id is automatically retrieved from the ExamSchedule. Supports bulk operations.",
    request=StudentAssignBulkSerializer,
    responses={
        201: OpenApiResponse(description="Students assigned successfully"),
        400: OpenApiResponse(description="Invalid request data"),
        409: OpenApiResponse(description="Some assignments already exist")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def assign_students_bulk(request):
    """Bulk assign students to teacher and exam"""
    
    serializer = StudentAssignBulkSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    student_ids = validated_data['student_ids']
    teacher_id = validated_data['teacher_id']
    schedule_id = validated_data['schedule_id']
    
    try:
        with transaction.atomic():
            # Get objects
            teacher = User.objects.get(id=teacher_id)
            schedule = ExamSchedule.objects.select_related('exam').get(id=schedule_id)
            exam = schedule.exam  # Get exam from schedule automatically
            students = Students.objects.filter(id__in=student_ids)
            
            # Track results
            created_assignments = []
            existing_assignments = []
            
            for student in students:
                assignment, created = StudentAssignTeacherExam.objects.get_or_create(
                    student=student,
                    teacher=teacher,
                    schedule=schedule,
                    defaults={'exam': exam}
                )
                
                if created:
                    created_assignments.append(assignment)
                else:
                    existing_assignments.append(assignment)
            
            # Prepare response
            response_data = {
                'success': True,
                'message': f'Bulk assignment completed. {len(created_assignments)} new assignments created.',
                'data': {
                    'created_count': len(created_assignments),
                    'existing_count': len(existing_assignments),
                    'total_processed': len(students),
                    'created_assignments': StudentAssignTeacherExamSerializer(created_assignments, many=True).data
                }
            }
            
            if existing_assignments:
                response_data['message'] += f' {len(existing_assignments)} assignments already existed.'
                response_data['data']['existing_assignments'] = StudentAssignTeacherExamSerializer(existing_assignments, many=True).data
            
            return Response(response_data, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating assignments: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='assign_student_single',
    tags=['Student Assignment'],
    summary="Assign single student to teacher and exam",
    description="Assign a single student to a teacher and exam. The exam_id is automatically retrieved from the ExamSchedule.",
    request=StudentAssignSingleSerializer,
    responses={
        201: OpenApiResponse(description="Student assigned successfully"),
        400: OpenApiResponse(description="Invalid request data"),
        409: OpenApiResponse(description="Assignment already exists")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def assign_student_single(request):
    """Assign single student to teacher and exam"""
    
    serializer = StudentAssignSingleSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    student_id = validated_data['student_id']
    teacher_id = validated_data['teacher_id']
    schedule_id = validated_data['schedule_id']
    
    try:
        # Get objects
        student = Students.objects.get(id=student_id)
        teacher = User.objects.get(id=teacher_id)
        schedule = ExamSchedule.objects.select_related('exam').get(id=schedule_id)
        exam = schedule.exam  # Get exam from schedule automatically
        
        # Create or get assignment
        assignment, created = StudentAssignTeacherExam.objects.get_or_create(
            student=student,
            teacher=teacher,
            schedule=schedule,
            defaults={'exam': exam}
        )
        
        if created:
            return Response({
                'success': True,
                'message': 'Student assigned successfully',
                'data': StudentAssignTeacherExamSerializer(assignment).data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Assignment already exists',
                'data': StudentAssignTeacherExamSerializer(assignment).data
            }, status=status.HTTP_409_CONFLICT)
            
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Teacher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except ExamSchedule.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Schedule not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='get_all_assignments',
    tags=['Student Assignment'],
    summary="Get all student assignments",
    description="Retrieve all student-teacher-exam assignments. Superadmin sees all, others see assignments filtered by department_shortname.",
    parameters=[
        OpenApiParameter(
            name='registration_semester',
            description='Filter assignments by the student registration semester',
            required=False,
            type=str,
        ),
        OpenApiParameter(name='search', description='Search by student, teacher, form ID, department, semester, exam, or schedule', required=False, type=str),
        OpenApiParameter(name='teacher_id', description='Filter by teacher ID', required=False, type=int),
        OpenApiParameter(name='exam_id', description='Filter by exam ID', required=False, type=int),
        OpenApiParameter(name='schedule_id', description='Filter by schedule ID', required=False, type=int),
        OpenApiParameter(name='date_filter', description='Use today to show assignments created today', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Rows per page', required=False, type=int),
    ],
    responses={
        200: OpenApiResponse(
            response=StudentAssignTeacherExamSerializer(many=True),
            description="Assignments retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_assignments(request):
    """Get all student assignments with role-based filtering"""
    
    user = request.user
    
    # Get the custom user and role information
    if hasattr(user, 'custom_user'):
        custom_user = user.custom_user
        
        # Check if user has a role
        if custom_user.role:
            role_name = custom_user.role.role_name.lower()
            
            # Check if superadmin - return all assignments
            if role_name == 'superadmin':
                assignments = StudentAssignTeacherExam.objects.all().select_related(
                    'student', 'teacher', 'exam', 'schedule'
                ).order_by('-created_at')
            else:
                # For non-superadmin users, filter by department_shortname
                if custom_user.department:
                    user_dept_shortname = custom_user.department.department_shortname
                    
                    # Get assignments where student's department matches user's department
                    assignments = StudentAssignTeacherExam.objects.filter(
                        student__department_shortname=user_dept_shortname
                    ).select_related('student', 'teacher', 'exam', 'schedule').order_by('-created_at')
                else:
                    # If user has no department assigned, return empty queryset
                    assignments = StudentAssignTeacherExam.objects.none()
        else:
            # If user has no role, return empty queryset
            assignments = StudentAssignTeacherExam.objects.none()
    else:
        # If no custom_user, return empty queryset for security
        assignments = StudentAssignTeacherExam.objects.none()

    filter_options = build_assignment_filter_options(assignments)
    assignments = apply_assignment_filters(assignments, request)
    
    page_assignments, pagination = paginate_queryset(assignments, request)
    serializer = StudentAssignTeacherExamSerializer(page_assignments, many=True)
    return Response({
        'success': True,
        'count': pagination['count'],
        'pagination': pagination,
        'filter_options': filter_options,
        'data': serializer.data,
        'message': 'Assignments retrieved successfully'
    })


@extend_schema(
    operation_id='delete_assignment',
    tags=['Student Assignment'],
    summary="Delete student assignment",
    description="Delete a specific student-teacher-exam assignment by ID.",
    responses={
        200: OpenApiResponse(description="Assignment deleted successfully"),
        404: OpenApiResponse(description="Assignment not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_assignment(request, assignment_id):
    """Delete a specific assignment"""
    
    try:
        assignment = StudentAssignTeacherExam.objects.get(id=assignment_id)
        assignment_info = {
            'student': assignment.student.username,
            'student_registration_semester': assignment.student.registration_semester,
            'teacher': assignment.teacher.username,
            'exam_id': assignment.exam.id
        }
        
        assignment.delete()
        
        return Response({
            'success': True,
            'message': 'Assignment deleted successfully',
            'deleted_assignment': assignment_info
        })
        
    except StudentAssignTeacherExam.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Assignment not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='delete_assignments_bulk',
    tags=['Student Assignment'],
    summary="Bulk delete student assignments",
    description="Delete multiple student-teacher-exam assignments by their IDs.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'assignment_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'List of assignment IDs to delete'
                }
            },
            'required': ['assignment_ids']
        }
    },
    responses={
        200: OpenApiResponse(description="Assignments deleted successfully"),
        400: OpenApiResponse(description="Invalid request data")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_assignments_bulk(request):
    """Bulk delete assignments"""
    
    assignment_ids = request.data.get('assignment_ids', [])
    
    if not assignment_ids:
        return Response({
            'success': False,
            'message': 'assignment_ids is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Get assignments that exist
            assignments = StudentAssignTeacherExam.objects.filter(id__in=assignment_ids)
            existing_ids = list(assignments.values_list('id', flat=True))
            missing_ids = set(assignment_ids) - set(existing_ids)
            
            # Delete existing assignments
            deleted_count = assignments.count()
            assignments.delete()
            
            response_data = {
                'success': True,
                'message': f'{deleted_count} assignments deleted successfully',
                'deleted_count': deleted_count,
                'deleted_ids': existing_ids
            }
            
            if missing_ids:
                response_data['message'] += f'. {len(missing_ids)} IDs were not found.'
                response_data['missing_ids'] = list(missing_ids)
            
            return Response(response_data)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error deleting assignments: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='get_student_assignments_by_teacher',
    tags=['Student Assignment'],
    summary="Get all student assignments for a specific teacher",
    description="Retrieve all students assigned to a specific teacher for exams",
    responses={
        200: OpenApiResponse(
            response=StudentAssignTeacherExamSerializer(many=True),
            description="Student assignments retrieved successfully"
        ),
        404: OpenApiResponse(description="Teacher not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_student_assignments_by_teacher(request, teacher_id):
    """Get all student assignments for a specific teacher"""
    
    # Check if teacher exists
    try:
        teacher = User.objects.get(id=teacher_id)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Teacher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Get all student assignments for this teacher
    assignments = StudentAssignTeacherExam.objects.filter(
        teacher_id=teacher_id
    ).select_related('student', 'teacher', 'exam', 'schedule').order_by('-created_at')

    filter_options = build_assignment_filter_options(assignments)
    assignments = apply_assignment_filters(assignments, request)
    
    page_assignments, pagination = paginate_queryset(assignments, request)
    serializer = StudentAssignTeacherExamSerializer(page_assignments, many=True)
    
    return Response({
        'success': True,
        'teacher': {
            'id': teacher.id,
            'username': teacher.username,
            'email': teacher.email
        },
        'count': pagination['count'],
        'pagination': pagination,
        'filter_options': filter_options,
        'data': serializer.data,
        'message': f'Found {pagination["count"]} student assignments for teacher {teacher.username}'
    })


@extend_schema(
    operation_id='get_available_schedules',
    tags=['Student Assignment'],
    summary="Get available exam schedules for assignment",
    description="Retrieve all active exam schedules that can be used for student assignment. Each schedule contains the exam information automatically.",
    responses={
        200: OpenApiResponse(
            response=ExamScheduleSerializer(many=True),
            description="Available schedules retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_available_schedules(request):
    """Get all available exam schedules for assignment"""
    
    user = request.user
    
    # Get the custom user and role information
    if hasattr(user, 'custom_user'):
        custom_user = user.custom_user
        
        # Check if user has a role
        if custom_user.role:
            role_name = custom_user.role.role_name.lower()
            
            # Check if superadmin - return all schedules
            if role_name == 'superadmin':
                schedules = ExamSchedule.objects.filter(
                    is_active=True
                ).select_related('exam').order_by('-created_at')
            else:
                # For non-superadmin users, filter by department_shortname
                if custom_user.department:
                    user_dept_shortname = custom_user.department.department_shortname
                    
                    # Get schedules where exam's department matches user's department
                    from ..models.exam_question import ExamQuestion
                    exam_ids = ExamQuestion.objects.filter(
                        department_shortname__icontains=user_dept_shortname
                    ).values_list('exam_id', flat=True).distinct()
                    
                    schedules = ExamSchedule.objects.filter(
                        is_active=True,
                        exam_id__in=exam_ids
                    ).select_related('exam').order_by('-created_at')
                else:
                    # If user has no department assigned, return empty queryset
                    schedules = ExamSchedule.objects.none()
        else:
            # If user has no role, return empty queryset
            schedules = ExamSchedule.objects.none()
    else:
        # If no custom_user, return empty queryset for security
        schedules = ExamSchedule.objects.none()
    
    serializer = ExamScheduleSerializer(schedules, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Available schedules retrieved successfully'
    })
