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
    exam_type = request.query_params.get('exam_type')

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
    if exam_type and exam_type != 'all':
        assignments = assignments.filter(exam__exam_type__iexact=exam_type)
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


def get_semester_mismatches(students, exam):
    """
    Students may only be assigned to exams of their own registration semester.
    Both sides are normalized so legacy rows with non-canonical semester text
    are compared fairly. Returns (mismatched_students, normalized_exam_semester).
    """
    exam_semester = normalize_semester_filter(exam.semester)
    mismatched = [
        {
            'id': student.id,
            'username': student.username,
            'f_id': student.f_id,
            'full_name': student.full_name,
            'registration_semester': student.registration_semester,
        }
        for student in students
        if normalize_semester_filter(student.registration_semester) != exam_semester
    ]
    return mismatched, exam_semester


def build_semester_mismatch_response(mismatched, exam_semester):
    return Response({
        'success': False,
        'message': (
            f'{len(mismatched)} student(s) are registered for a different semester '
            f'than the exam ({exam_semester}). No assignments were created.'
        ),
        'error_code': 'SEMESTER_MISMATCH',
        'exam_semester': exam_semester,
        'mismatched_students': mismatched,
    }, status=status.HTTP_400_BAD_REQUEST)


def get_duplicate_semester_assignments(students, exam):
    """
    A student may sit only one exam per semester. Flags students who already
    hold ANY assignment in this exam's semester — including another schedule
    of the same exam, which previously slipped through and allowed duplicate
    assignments for students who had already taken the exam.
    """
    exam_semester = normalize_semester_filter(exam.semester)
    duplicated = []
    for student in students:
        existing = (
            StudentAssignTeacherExam.objects.filter(student=student)
            .select_related('exam')
        )
        if any(
            normalize_semester_filter(assignment.exam.semester) == exam_semester
            for assignment in existing
        ):
            duplicated.append({
                'id': student.id,
                'username': student.username,
                'f_id': student.f_id,
                'full_name': student.full_name,
                'registration_semester': student.registration_semester,
            })
    return duplicated, exam_semester


def build_duplicate_semester_response(duplicated, exam_semester):
    return Response({
        'success': False,
        'message': (
            f'{len(duplicated)} student(s) are already assigned to an exam in '
            f'{exam_semester}. A student can only take one exam per semester. '
            'No assignments were created.'
        ),
        'error_code': 'DUPLICATE_SEMESTER_ASSIGNMENT',
        'exam_semester': exam_semester,
        'mismatched_students': duplicated,
    }, status=status.HTTP_400_BAD_REQUEST)


def get_faculty_and_department_mismatches(students, exam):
    """
    Validates faculty-level eligibility for both CENTRAL and SCHEDULED exams,
    and department match for SCHEDULED exams.
    """
    from ..services.access_control import get_faculty_for_department, get_departments_for_faculty
    from ..models import Department, Faculty

    applicable_faculty = getattr(exam, 'faculty_ref', None)
    if not applicable_faculty and exam.faculty:
        applicable_faculty = Faculty.objects.filter(
            Q(faculty_shortname__iexact=exam.faculty) | Q(faculty_name__iexact=exam.faculty)
        ).first()

    exam_dept = None
    if exam.department and not exam.department.startswith('Central'):
        exam_dept = Department.objects.filter(
            Q(department_name__iexact=exam.department) | Q(department_shortname__iexact=exam.department)
        ).first()
        if not applicable_faculty and exam_dept:
            applicable_faculty = get_faculty_for_department(exam_dept.id)

    faculty_dept_ids = set()
    if applicable_faculty:
        faculty_dept_ids = set(get_departments_for_faculty(applicable_faculty.id))

    mismatched = []
    for student in students:
        # Extract student's department IDs from complete department_choices
        student_dept_ids = set(
            c['department_id']
            for c in (student.department_choices or [])
            if isinstance(c, dict) and 'department_id' in c
        )
        if not student_dept_ids and student.department_shortname:
            s_dept = Department.objects.filter(department_shortname__iexact=student.department_shortname).first()
            if s_dept:
                student_dept_ids.add(s_dept.id)

        if applicable_faculty:
            student_faculty_id = getattr(student, 'faculty_id', None)
            dept_matches_faculty = bool(student_dept_ids & faculty_dept_ids)
            faculty_matches = (student_faculty_id == applicable_faculty.id) or dept_matches_faculty

            if not faculty_matches:
                mismatched.append({
                    'id': student.id,
                    'username': student.username,
                    'f_id': student.f_id,
                    'full_name': student.full_name,
                    'reason': f"Student does not belong to faculty {applicable_faculty.faculty_name} ({applicable_faculty.faculty_shortname})"
                })
                continue

        # For SCHEDULED exams: department-specific constraint
        if (getattr(exam, 'exam_type', '') or '').upper() == 'SCHEDULED' and exam_dept:
            if exam_dept.id not in student_dept_ids:
                mismatched.append({
                    'id': student.id,
                    'username': student.username,
                    'f_id': student.f_id,
                    'full_name': student.full_name,
                    'reason': f"Scheduled exam requires student with department {exam_dept.department_shortname} in their department choice list"
                })

    return mismatched


def build_faculty_mismatch_response(mismatches):
    return Response({
        'success': False,
        'message': (
            f'{len(mismatches)} student(s) do not meet the faculty or department eligibility '
            'conditions for this exam schedule. No assignments were created.'
        ),
        'error_code': 'FACULTY_ELIGIBILITY_MISMATCH',
        'mismatched_students': mismatches,
    }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='assign_students_bulk',
    tags=['Student Assignment'],
    summary="Bulk assign students to teacher and exam",
    description="Assign multiple students to a teacher and exam in one request. The exam_id is automatically retrieved from the ExamSchedule. Supports bulk operations.",
    request=StudentAssignBulkSerializer,
    responses={
        201: OpenApiResponse(description="Students assigned successfully"),
        400: OpenApiResponse(
            description=(
                "Invalid request data, or one or more students are registered for a "
                "different semester than the exam (error_code SEMESTER_MISMATCH)"
            )
        ),
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

            # All-or-nothing: reject the whole request if any student belongs to a
            # different semester than the exam, so cross-semester rows never exist.
            mismatched, exam_semester = get_semester_mismatches(students, exam)
            if mismatched:
                return build_semester_mismatch_response(mismatched, exam_semester)

            duplicated, exam_semester = get_duplicate_semester_assignments(students, exam)
            if duplicated:
                return build_duplicate_semester_response(duplicated, exam_semester)

            faculty_mismatches = get_faculty_and_department_mismatches(students, exam)
            if faculty_mismatches:
                return build_faculty_mismatch_response(faculty_mismatches)

            # Access scope authorization check
            custom_user = getattr(request.user, 'custom_user', None)
            from ..services.access_control import get_user_access_scope
            scope = get_user_access_scope(custom_user)
            if not scope['is_global']:
                user_dept_ids = set(scope.get('department_ids') or [])
                user_faculty_id = getattr(custom_user, 'faculty_id', None)
                unauthorized_students = []
                for s in students:
                    s_dept_ids = set(
                        c['department_id']
                        for c in (s.department_choices or [])
                        if isinstance(c, dict) and 'department_id' in c
                    )
                    if not s_dept_ids and s.department_shortname:
                        sd = Department.objects.filter(department_shortname__iexact=s.department_shortname).first()
                        if sd:
                            s_dept_ids.add(sd.id)
                    has_access = bool(s_dept_ids & user_dept_ids)
                    if not has_access and user_faculty_id and getattr(s, 'faculty_id', None) == user_faculty_id:
                        has_access = True
                    if not has_access:
                        unauthorized_students.append(s.username)
                if unauthorized_students:
                    return Response({
                        'success': False,
                        'message': f"You do not have authorization to assign student(s): {', '.join(unauthorized_students)}",
                        'error_code': 'UNAUTHORIZED_STUDENT_ASSIGNMENT'
                    }, status=status.HTTP_403_FORBIDDEN)

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
        400: OpenApiResponse(
            description=(
                "Invalid request data, or the student is registered for a different "
                "semester than the exam (error_code SEMESTER_MISMATCH)"
            )
        ),
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

        mismatched, exam_semester = get_semester_mismatches([student], exam)
        if mismatched:
            return build_semester_mismatch_response(mismatched, exam_semester)

        duplicated, exam_semester = get_duplicate_semester_assignments([student], exam)
        if duplicated:
            return build_duplicate_semester_response(duplicated, exam_semester)

        faculty_mismatches = get_faculty_and_department_mismatches([student], exam)
        if faculty_mismatches:
            return build_faculty_mismatch_response(faculty_mismatches)

        # Access scope authorization check
        custom_user = getattr(request.user, 'custom_user', None)
        from ..services.access_control import get_user_access_scope
        scope = get_user_access_scope(custom_user)
        if not scope['is_global']:
            user_dept_ids = set(scope.get('department_ids') or [])
            user_faculty_id = getattr(custom_user, 'faculty_id', None)
            s_dept_ids = set(
                c['department_id']
                for c in (student.department_choices or [])
                if isinstance(c, dict) and 'department_id' in c
            )
            if not s_dept_ids and student.department_shortname:
                sd = Department.objects.filter(department_shortname__iexact=student.department_shortname).first()
                if sd:
                    s_dept_ids.add(sd.id)
            has_access = bool(s_dept_ids & user_dept_ids)
            if not has_access and user_faculty_id and getattr(student, 'faculty_id', None) == user_faculty_id:
                has_access = True
            if not has_access:
                return Response({
                    'success': False,
                    'message': f"You do not have authorization to assign student {student.username}",
                    'error_code': 'UNAUTHORIZED_STUDENT_ASSIGNMENT'
                }, status=status.HTTP_403_FORBIDDEN)

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
    custom_user = getattr(user, 'custom_user', None)

    from ..services.access_control import get_user_access_scope
    from ..models import Department
    scope = get_user_access_scope(custom_user)

    if scope['is_global']:
        assignments = StudentAssignTeacherExam.objects.all().select_related(
            'student', 'teacher', 'exam', 'schedule'
        ).order_by('-created_at')
    else:
        dept_ids = scope['department_ids'] or []
        valid_depts = Department.objects.filter(id__in=dept_ids)
        dept_shortnames = [d.department_shortname for d in valid_depts]

        allowed_faculty_ids = set()
        if getattr(custom_user, 'faculty_id', None):
            allowed_faculty_ids.add(custom_user.faculty_id)

        q_student_choices = Q()
        for d_id in dept_ids:
            q_student_choices |= Q(student__department_choices__contains=[{'department_id': d_id}])

        q_student_legacy = (
            Q(student__department_choices=[]) | Q(student__department_choices__isnull=True)
        ) & Q(student__department_shortname__in=dept_shortnames)

        q_assign = q_student_choices | q_student_legacy | Q(exam__department__in=dept_shortnames)
        if allowed_faculty_ids:
            q_assign |= Q(student__faculty_id__in=allowed_faculty_ids) | Q(exam__faculty_ref_id__in=allowed_faculty_ids)

        assignments = StudentAssignTeacherExam.objects.filter(q_assign).select_related(
            'student', 'teacher', 'exam', 'schedule'
        ).distinct().order_by('-created_at')

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
    custom_user = getattr(user, 'custom_user', None)

    from ..services.access_control import get_user_access_scope, get_faculty_for_department
    from ..models import Department, ExamQuestion

    scope = get_user_access_scope(custom_user)
    exam_type = request.query_params.get('exam_type')

    if scope['is_global']:
        schedules = ExamSchedule.objects.filter(is_active=True)
    else:
        dept_ids = scope['department_ids'] or []
        user_faculty_id = getattr(custom_user, 'faculty_id', None)

        if not dept_ids and not user_faculty_id:
            schedules = ExamSchedule.objects.none()
        else:
            valid_depts = Department.objects.filter(id__in=dept_ids)
            dept_shortnames = [d.department_shortname for d in valid_depts]

            allowed_faculty_ids = set()
            if user_faculty_id:
                allowed_faculty_ids.add(user_faculty_id)
            for dept in valid_depts:
                parent_fac = get_faculty_for_department(dept.id)
                if parent_fac:
                    allowed_faculty_ids.add(parent_fac.id)

            exam_ids_with_matching_questions = ExamQuestion.objects.filter(
                department_shortname__in=dept_shortnames
            ).values_list('exam_id', flat=True).distinct()

            q_schedules = (
                Q(exam_id__in=exam_ids_with_matching_questions) |
                Q(exam__department__in=[d.department_name for d in valid_depts]) |
                Q(exam__department__in=dept_shortnames)
            )
            if allowed_faculty_ids:
                q_schedules |= Q(exam__exam_type__iexact='CENTRAL', exam__faculty_ref_id__in=allowed_faculty_ids)

            schedules = ExamSchedule.objects.filter(is_active=True).filter(q_schedules).distinct()

    if exam_type and exam_type != 'all':
        schedules = schedules.filter(exam__exam_type__iexact=exam_type)

    schedules = schedules.select_related('exam', 'exam__faculty_ref').prefetch_related('exam__exam_questions').order_by('-created_at')
    
    serializer = ExamScheduleSerializer(schedules, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Available schedules retrieved successfully'
    })


@extend_schema(
    operation_id='get_assigned_student_ids',
    tags=['Student Assignment'],
    summary="Get ids of all students holding a written-exam assignment",
    description="Unpaginated distinct student ids. Used by the assign page to compute which students are still available.",
    responses={200: OpenApiResponse(description="Assigned student ids retrieved successfully")}
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_assigned_student_ids(request):
    """Distinct student ids with an existing assignment (unpaginated).

    Availability must be computed against this full set — computing it against
    the paginated list made students whose rows fell off page 1 look
    available for reassignment again.
    """
    student_ids = list(
        StudentAssignTeacherExam.objects.values_list('student_id', flat=True).distinct()
    )
    return Response({'success': True, 'student_ids': student_ids})
