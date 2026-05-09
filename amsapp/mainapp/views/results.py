from collections import defaultdict

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ..models import (
    PublishedExam, Exam, Students, Submission,
    StudentAssignTeacherExam, User, ExamQuestion, VivaAssignment
)
from ..models.viva_marks import VivaMarks
from ..serializers.results import (
    PublishedExamSerializer, TogglePublishSerializer, 
    EnhancedExamResultSerializer, ResultsSummarySerializer
)
from ..authentication import CustomJWTAuthentication
from ..utils import build_subject_result_rows, calculate_submission_summary, normalize_semester_filter


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
    page_size = 20
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
    
    user = request.user
    semester_filter = normalize_semester_filter(request.query_params.get('semester', None))
    
    # Check permissions
    if hasattr(user, 'custom_user'):
        custom_user = user.custom_user
        
        # Check if user has a role
        if custom_user.role:
            role_name = custom_user.role.role_name.lower()
            
            # If not superadmin, ensure they can only see their own results
            if role_name != 'superadmin' and custom_user.id != teacher_id:
                return Response({
                    'success': False,
                    'message': 'You can only view your own results'
                }, status=status.HTTP_403_FORBIDDEN)
        else:
            return Response({
                'success': False,
                'message': 'Access denied'
            }, status=status.HTTP_403_FORBIDDEN)
    else:
        return Response({
            'success': False,
            'message': 'Access denied'
        }, status=status.HTTP_403_FORBIDDEN)
    
    try:
        teacher = User.objects.get(id=teacher_id)
        assignments = StudentAssignTeacherExam.objects.filter(
            teacher=teacher
        ).select_related('student', 'exam')
        if semester_filter:
            assignments = assignments.filter(exam__semester__icontains=semester_filter)

        assignment_rows = list(assignments.order_by('-created_at', '-id'))
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

        if not pair_order:
            paginator = ResultsPagination()
            empty_page = paginator.paginate_queryset([], request)
            response_data = {
                'pagination': {
                    'count': 0,
                    'current_page': 1,
                    'total_pages': 1,
                    'page_size': paginator.get_page_size(request),
                    'has_next': False,
                    'has_previous': False
                },
                'results': empty_page if empty_page is not None else [],
                'filters': {
                    'semester': semester_filter,
                    'teacher_id': teacher_id,
                    'teacher_name': teacher.username
                }
            }
            return Response({
                'success': True,
                'data': response_data,
                'message': f'Found 0 results for teacher {teacher.username}'
            })

        exam_ids = list(exam_map.keys())
        student_ids = list(student_map.keys())

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

        results_data = []
        for pair_key in pair_order:
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
                'viva_marks': viva_marks_data
            })

        # Apply pagination
        paginator = ResultsPagination()
        page = paginator.paginate_queryset(results_data, request)

        # Prepare pagination info
        pagination_info = {
            'count': len(results_data),
            'current_page': paginator.page.number,
            'total_pages': paginator.page.paginator.num_pages,
            'page_size': paginator.page_size,
            'has_next': paginator.page.has_next(),
            'has_previous': paginator.page.has_previous()
        }

        # Prepare filters info
        filters_info = {
            'semester': semester_filter,
            'teacher_id': teacher_id,
            'teacher_name': teacher.username
        }

        response_data = {
            'pagination': pagination_info,
            'results': page if page is not None else results_data,
            'filters': filters_info
        }

        return Response({
            'success': True,
            'data': response_data,
            'message': f'Found {len(results_data)} results for teacher {teacher.username}'
        })

    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Teacher not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='get_published_exams',
    tags=['Exam Results'],
    summary="Get all published exams",
    description="Get list of all exams with their publication status",
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
    
    serializer = PublishedExamSerializer(published_exams, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Published exams retrieved successfully'
    })
