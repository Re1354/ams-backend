import logging
from collections import defaultdict

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import (
    PublishedExam, Exam, Students, Submission,
    StudentAssignTeacherExam, User, ExamQuestion, VivaAssignment,
    AdmissionResult,
)
from ..models.viva_marks import VivaMarks
from ..serializers.results import (
    PublishedExamSerializer, TogglePublishSerializer, 
    EnhancedExamResultSerializer, ResultsSummarySerializer
)
from ..authentication import CustomJWTAuthentication
from ..utils import (
    build_subject_result_rows,
    calculate_submission_summary,
    normalize_semester_filter,
    paginate_queryset,
)

logger = logging.getLogger(__name__)


@extend_schema(
    operation_id='toggle_exam_publication',
    tags=['Exam Results'],
    summary="Toggle exam result publication status",
    description="Toggle the publication status of exam results. Same endpoint handles both publish and unpublish actions.",
    request=TogglePublishSerializer,
    responses={
        200: OpenApiResponse(
            response=PublishedExamSerializer,
            description="Publication status toggled successfully"
        ),
        404: OpenApiResponse(description="Exam not found"),
        400: OpenApiResponse(description="Invalid request data")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def toggle_exam_publication(request):
    """Toggle exam result publication status"""
    
    serializer = TogglePublishSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exam_id = serializer.validated_data['exam_id']
    
    try:
        exam = Exam.objects.get(id=exam_id)
        
        from ..services.access_control import get_user_access_scope
        from ..models import Department
        user = getattr(request.user, 'custom_user', None)
        scope = get_user_access_scope(user)
        
        if not scope['is_global']:
            dept = Department.objects.filter(
                Q(department_name__iexact=exam.department) | Q(department_shortname__iexact=exam.department)
            ).first()
            if not dept or dept.id not in (scope['department_ids'] or []):
                return Response(
                    {"success": False, "message": "You do not have access to this exam."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Get or create published exam record
        published_exam, created = PublishedExam.objects.get_or_create(
            exam=exam,
            defaults={'is_published': False}
        )
        
        # Toggle the publication status
        published_exam.is_published = not published_exam.is_published
        published_exam.save()
        
        action = "published" if published_exam.is_published else "unpublished"
        
        return Response({
            'success': True,
            'message': f'Exam results {action} successfully',
            'data': PublishedExamSerializer(published_exam).data
        })
        
    except Exam.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Exam not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='get_student_exam_result_enhanced',
    tags=['Exam Results'],
    summary="Get enhanced student exam result with subject breakdown",
    description="Get detailed exam result for a student including subject-wise breakdown. Results are only available if published.",
    responses={
        200: OpenApiResponse(
            response=EnhancedExamResultSerializer,
            description="Exam result retrieved successfully"
        ),
        403: OpenApiResponse(description="Results not published yet"),
        404: OpenApiResponse(description="Student or exam not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_student_exam_result_enhanced(request, exam_id, student_id):
    """Get enhanced student exam result with subject breakdown"""
    
    try:
        exam = Exam.objects.get(id=exam_id)
        student = Students.objects.get(id=student_id)
        
        from ..services.access_control import get_user_access_scope
        from ..models import Department
        user = getattr(request.user, 'custom_user', None)
        scope = get_user_access_scope(user)
        
        if not scope['is_global']:
            dept = Department.objects.filter(
                Q(department_name__iexact=exam.department) | Q(department_shortname__iexact=exam.department)
            ).first()
            if not dept or dept.id not in (scope['department_ids'] or []):
                return Response(
                    {"success": False, "message": "You do not have access to this exam's results."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Check if results are published
        try:
            published_exam = PublishedExam.objects.get(exam=exam)
            if not published_exam.is_published:
                return Response({
                    'success': False,
                    'message': 'Results are not published yet'
                }, status=status.HTTP_403_FORBIDDEN)
        except PublishedExam.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Results are not published yet'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get student's submissions for this exam
        submissions = Submission.objects.filter(
            student=student,
            exam=exam
        ).select_related('question')
        
        if not submissions.exists():
            return Response({
                'success': False,
                'message': 'No submissions found for this student and exam'
            }, status=status.HTTP_404_NOT_FOUND)
        
        summary = calculate_submission_summary(exam, submissions)
        subject_rows = build_subject_result_rows(exam, submissions)
        
        # Prepare response
        response_data = {
            'student_id': student.id,
            'exam_id': exam.id,
            'student_name': student.full_name or student.username,
            'exam_details': {
                'department': exam.department,
                'semester': exam.semester,
                'total_questions': exam.total_questions
            },
            'results': {
                'correct_answers': summary['correct_answers'],
                'wrong_answers': summary['wrong_answers'],
                'score_percentage': summary['score_percentage']
            },
            'subjects': subject_rows
        }
        
        return Response({
            'success': True,
            'data': response_data
        })
        
    except Exam.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Exam not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Students.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Student not found'
        }, status=status.HTTP_404_NOT_FOUND)


class ResultsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100


def _calculate_submission_summary_cached(total_marks, submissions):
    total_attempted = len(submissions)
    correct_answers = sum(1 for submission in submissions if submission.is_correct)
    wrong_answers = total_attempted - correct_answers
    obtained_marks = sum(
        getattr(submission.question, "marks", 0)
        for submission in submissions
        if submission.is_correct
    )
    score_percentage = round((obtained_marks / total_marks) * 100, 2) if total_marks > 0 else 0

    return {
        'correct_answers': correct_answers,
        'wrong_answers': wrong_answers,
        'score_percentage': score_percentage,
    }


def _build_subject_result_rows_cached(question_rows, submissions):
    submissions_by_question = {submission.question_id: submission for submission in submissions}
    subject_data = defaultdict(
        lambda: {
            'subject_id': '',
            'subject_name': '',
            'total_questions': 0,
            'correct_answers': 0,
            'wrong_answers': 0,
            '_total_marks': 0,
            '_obtained_marks': 0,
        }
    )

    for question in question_rows:
        subject_name = question['subject']
        row = subject_data[subject_name]
        row['subject_id'] = subject_name
        row['subject_name'] = subject_name
        row['total_questions'] += 1
        row['_total_marks'] += question['marks'] or 0

        submission = submissions_by_question.get(question['id'])
        if not submission:
            continue

        if submission.is_correct:
            row['correct_answers'] += 1
            row['_obtained_marks'] += question['marks'] or 0
        else:
            row['wrong_answers'] += 1

    rows = []
    for row in subject_data.values():
        total_marks = row.pop('_total_marks')
        obtained_marks = row.pop('_obtained_marks')
        row['score_percentage'] = (
            round((obtained_marks / total_marks) * 100, 2) if total_marks > 0 else 0
        )
        rows.append(row)

    rows.sort(key=lambda item: item['subject_name'])
    return rows


@extend_schema(
    operation_id='get_all_results_by_teacher',
    tags=['Exam Results'],
    summary="Get all exam results summary for a teacher",
    description="Get paginated results summary for all students under a teacher. Superadmin sees all results, others see results based on teacher_id.",
    parameters=[
        OpenApiParameter(name='semester', description='Filter by semester', required=False, type=str),
        OpenApiParameter(name='search', description='Search by student, form ID, department, semester, or exam ID', required=False, type=str),
        OpenApiParameter(name='department', description='Filter by exam department', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Number of results per page', required=False, type=int),
    ],
    responses={
        200: OpenApiResponse(
            response=ResultsSummarySerializer,
            description="Results summary retrieved successfully"
        ),
        404: OpenApiResponse(description="Teacher not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_results_by_teacher(request, teacher_id):
    """Get all exam results summary for a teacher with pagination and filtering"""
    
    from ..services.access_control import get_user_access_scope
    from ..models import Department
    
    user = getattr(request.user, 'custom_user', None)
    scope = get_user_access_scope(user)
    
    semester_filter = normalize_semester_filter(request.query_params.get('semester', None))
    search = request.query_params.get('search')
    department_filter = request.query_params.get('department')
    
    # Check permissions: if not global, they can only view their own OR we filter by their departments later
    # Let's enforce that non-global users can only view their own results, unless they have department access.
    # We will filter viva_assignments by department below.
    
    try:
        teacher = User.objects.get(id=teacher_id)
        viva_assignments = VivaAssignment.objects.filter(
            teacher=teacher
        ).select_related('student', 'exam')
        
        if not scope['is_global']:
            # If they are viewing another teacher, restrict to their permitted departments
            if user and user.id != teacher_id:
                valid_depts = Department.objects.filter(id__in=(scope['department_ids'] or []))
                dept_names = [d.department_name for d in valid_depts] + [d.department_shortname for d in valid_depts]
                q_dept = Q()
                for name in dept_names:
                    q_dept |= Q(exam__department__iexact=name)
                
                # If they have no valid depts, q_dept is empty and will match nothing
                if not scope['department_ids']:
                    viva_assignments = VivaAssignment.objects.none()
                else:
                    viva_assignments = viva_assignments.filter(q_dept)
                    
        if semester_filter:
            viva_assignments = viva_assignments.filter(exam__semester__icontains=semester_filter)
        if department_filter:
            viva_assignments = viva_assignments.filter(exam__department__icontains=department_filter)
        if search:
            normalized_search_semester = normalize_semester_filter(search)
            search_query = (
                Q(student__username__icontains=search)
                | Q(student__full_name__icontains=search)
                | Q(student__f_id__icontains=search)
                | Q(student__email__icontains=search)
                | Q(student__department_shortname__icontains=search)
                | Q(student__registration_semester__icontains=normalized_search_semester)
                | Q(exam__department__icontains=search)
                | Q(exam__semester__icontains=normalized_search_semester)
            )
            if str(search).isdigit():
                search_query |= Q(exam_id=int(search))
            viva_assignments = viva_assignments.filter(search_query)

        assignment_rows = list(viva_assignments.order_by('-created_at', '-id'))
        pair_order = []
        pair_map = {}
        exam_map = {}
        student_map = {}

        for assignment in assignment_rows:
            pair_key = (assignment.exam_id, assignment.student_id)
            if pair_key in pair_map:
                continue
            pair_map[pair_key] = assignment
            pair_order.append(pair_key)
            exam_map[assignment.exam_id] = assignment.exam
            student_map[assignment.student_id] = assignment.student

        submitted_pairs = set(
            Submission.objects.filter(
                exam_id__in=exam_map.keys(),
                student_id__in=student_map.keys(),
            )
            .values_list('exam_id', 'student_id')
            .distinct()
        )
        pair_order = [pair_key for pair_key in pair_order if pair_key in submitted_pairs]

        if not pair_order:
            _, pagination_info = paginate_queryset([], request)
            response_data = {
                'pagination': pagination_info,
                'results': [],
                'filters': {
                    'semester': semester_filter,
                    'search': search,
                    'department': department_filter,
                    'teacher_id': teacher_id,
                    'teacher_name': teacher.username
                }
            }
            return Response({
                'success': True,
                'data': response_data,
                'message': f'Found 0 results for teacher {teacher.username}'
            })

        page_pairs, pagination_info = paginate_queryset(pair_order, request)
        page_pairs = list(page_pairs)

        exam_ids = sorted({exam_id for exam_id, _ in page_pairs})
        student_ids = sorted({student_id for _, student_id in page_pairs})

        exam_question_rows = defaultdict(list)
        exam_total_marks = defaultdict(float)
        for question in ExamQuestion.objects.filter(exam_id__in=exam_ids).values(
            'exam_id', 'id', 'subject', 'marks'
        ):
            exam_question_rows[question['exam_id']].append(question)
            exam_total_marks[question['exam_id']] += float(question['marks'] or 0)

        submissions_by_pair = defaultdict(list)
        submissions = Submission.objects.filter(
            exam_id__in=exam_ids,
            student_id__in=student_ids,
        ).select_related('question')
        for submission in submissions:
            submissions_by_pair[(submission.exam_id, submission.student_id)].append(submission)

        viva_assignments_by_pair = {}
        viva_assignments = VivaAssignment.objects.filter(
            exam_id__in=exam_ids,
            student_id__in=student_ids,
            teacher=teacher,
        ).order_by('-updated_at', '-created_at', '-id')
        for viva_assignment in viva_assignments:
            pair_key = (viva_assignment.exam_id, viva_assignment.student_id)
            viva_assignments_by_pair.setdefault(pair_key, viva_assignment)

        legacy_viva_by_student = {
            viva.student_id: viva
            for viva in VivaMarks.objects.filter(student_id__in=student_ids)
        }

        # Admission status per (exam, student). ACCEPTED when admitted, else the
        # stored result_status; PENDING when the board hasn't been calculated.
        admission_status_by_pair = {}
        for admission in AdmissionResult.objects.filter(
            exam_id__in=exam_ids, student_id__in=student_ids
        ).values('exam_id', 'student_id', 'result_status', 'is_admitted'):
            pair_key = (admission['exam_id'], admission['student_id'])
            admission_status_by_pair[pair_key] = (
                'ACCEPTED' if admission['is_admitted'] else admission['result_status']
            )

        results_data = []
        for pair_key in page_pairs:
            exam_id, student_id = pair_key
            exam = exam_map[exam_id]
            student = student_map[student_id]
            submission_list = submissions_by_pair.get(pair_key, [])

            if not submission_list:
                continue

            summary = _calculate_submission_summary_cached(
                exam_total_marks.get(exam_id, 0),
                submission_list,
            )
            subject_rows = _build_subject_result_rows_cached(
                exam_question_rows.get(exam_id, []),
                submission_list,
            )

            viva_assignment = viva_assignments_by_pair.get(pair_key)
            if viva_assignment:
                viva_marks_data = {
                    'marks': viva_assignment.total_marks,
                    'rubrics_marks': viva_assignment.rubric_scores,
                    'remarks': viva_assignment.remarks
                }
            else:
                legacy_viva = legacy_viva_by_student.get(student_id)
                viva_marks_data = {
                    'marks': legacy_viva.marks if legacy_viva else 0,
                    'rubrics_marks': legacy_viva.rubrics_marks if legacy_viva else {},
                    'remarks': legacy_viva.remarks if legacy_viva else None
                }

            results_data.append({
                'student_id': student.id,
                'student_f_id': student.f_id,
                'exam_id': exam.id,
                'student_name': student.full_name or student.username,
                'exam_details': {
                    'department': exam.department,
                    'semester': exam.semester,
                    'total_questions': exam.total_questions
                },
                'results': summary,
                'subjects': subject_rows,
                'viva_marks': viva_marks_data,
                'result_status': admission_status_by_pair.get(pair_key, 'PENDING'),
            })

        # Prepare filters info
        filters_info = {
            'semester': semester_filter,
            'search': search,
            'department': department_filter,
            'teacher_id': teacher_id,
            'teacher_name': teacher.username
        }

        response_data = {
            'pagination': pagination_info,
            'results': results_data,
            'filters': filters_info
        }

        return Response({
            'success': True,
            'data': response_data,
            'message': f'Found {pagination_info["count"]} results for teacher {teacher.username}'
        })

    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Teacher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        logger.exception(
            "Failed to get results for teacher_id=%s with params=%s",
            teacher_id,
            dict(request.query_params),
        )
        return Response({
            'success': False,
            'message': 'Failed to load exam results',
            'error': str(exc),
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='get_published_exams',
    tags=['Exam Results'],
    summary="Get all published exams",
    description="Get list of all exams with their publication status",
    parameters=[
        OpenApiParameter(name='search', description='Search by exam ID, department, or semester', required=False, type=str),
        OpenApiParameter(name='department', description='Filter by exam department', required=False, type=str),
        OpenApiParameter(name='semester', description='Filter by exam semester', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Rows per page', required=False, type=int),
    ],
    responses={
        200: OpenApiResponse(
            response=PublishedExamSerializer(many=True),
            description="Published exams retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_published_exams(request):
    """Get all published exams"""
    
    user = request.user
    
    # Role-based filtering
    if hasattr(user, 'custom_user'):
        custom_user = user.custom_user
        
        if custom_user.role:
            role_name = custom_user.role.role_name.lower()
            
            if role_name == 'superadmin':
                # Superadmin sees all published exams
                published_exams = PublishedExam.objects.all().select_related('exam')
            else:
                # Non-superadmin sees exams filtered by department
                if custom_user.department:
                    user_dept_shortname = custom_user.department.department_shortname
                    
                    # Get exam IDs that match user's department
                    from ..models.exam_question import ExamQuestion
                    exam_ids = ExamQuestion.objects.filter(
                        department_shortname__icontains=user_dept_shortname
                    ).values_list('exam_id', flat=True).distinct()
                    
                    published_exams = PublishedExam.objects.filter(
                        exam_id__in=exam_ids
                    ).select_related('exam')
                else:
                    published_exams = PublishedExam.objects.none()
        else:
            published_exams = PublishedExam.objects.none()
    else:
        published_exams = PublishedExam.objects.none()

    search = request.query_params.get('search')
    department = request.query_params.get('department')
    semester = request.query_params.get('semester')
    filter_options = {
        'departments': list(
            published_exams.exclude(exam__department__isnull=True)
            .exclude(exam__department='')
            .order_by('exam__department')
            .values_list('exam__department', flat=True)
            .distinct()
        ),
        'semesters': list(
            published_exams.exclude(exam__semester__isnull=True)
            .exclude(exam__semester='')
            .order_by('exam__semester')
            .values_list('exam__semester', flat=True)
            .distinct()
        ),
    }

    if search:
        normalized_search_semester = normalize_semester_filter(search)
        search_query = (
            Q(exam__department__icontains=search)
            | Q(exam__semester__icontains=normalized_search_semester)
        )
        if str(search).isdigit():
            search_query |= Q(exam_id=int(search))
        published_exams = published_exams.filter(search_query)
    if department:
        published_exams = published_exams.filter(exam__department__icontains=department)
    if semester:
        published_exams = published_exams.filter(exam__semester__icontains=normalize_semester_filter(semester))
    
    published_exams = published_exams.order_by('-updated_at', '-id')
    page_published_exams, pagination = paginate_queryset(published_exams, request)
    serializer = PublishedExamSerializer(page_published_exams, many=True)
    return Response({
        'success': True,
        'count': pagination['count'],
        'pagination': pagination,
        'filter_options': filter_options,
        'data': serializer.data,
        'message': 'Published exams retrieved successfully'
    })
