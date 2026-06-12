from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiExample, OpenApiParameter
from collections import OrderedDict

from ..models import Exam, ExamSchedule, VivaAssignment
from ..serializers import ExamScheduleSerializer, CreateExamScheduleSerializer
from ..serializers.viva_assign import VivaAssignmentSerializer
from ..authentication import CustomJWTAuthentication
from ..utils import normalize_semester_filter


@extend_schema(
    summary="Get all exam schedules with exam details",
    description="Retrieve exam schedules with detailed exam information. Role-based filtering: superadmin sees all schedules, other users only see schedules for exams matching their department_shortname.",
    tags=['Schedule'],
    parameters=[
        OpenApiParameter(name='search', description='Search by schedule ID, exam ID, department, or semester', required=False, type=str),
        OpenApiParameter(name='department', description='Filter by exam department', required=False, type=str),
        OpenApiParameter(name='semester', description='Filter by exam semester', required=False, type=str),
        OpenApiParameter(name='date_filter', description='Use today to show schedules starting today', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Rows per page', required=False, type=int),
    ],
    responses={200: ExamScheduleSerializer(many=True)}
)
class AllSchedulesView(generics.ListCreateAPIView):
    """List exam schedules with role-based filtering and create new schedules"""
    serializer_class = ExamScheduleSerializer
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Filter schedules based on user role and department:
        - superadmin: All schedules
        - Other users: Only schedules for exams that have questions matching their department_shortname
        """
        user = self.request.user
        
        # Get the custom user and role information
        queryset = ExamSchedule.objects.none()
        scoped_queryset_set = False

        if hasattr(user, 'custom_user'):
            custom_user = user.custom_user
            
            # Check if user has a role
            if custom_user.role:
                role_name = custom_user.role.role_name.lower()
                
                # Check if superadmin - return all schedules
                if role_name == 'superadmin':
                    queryset = ExamSchedule.objects.all()
                    scoped_queryset_set = True
            
            # For non-superadmin users, filter by department_shortname
            if not scoped_queryset_set and custom_user.department:
                from ..models import ExamQuestion
                user_dept_shortname = custom_user.department.department_shortname
                
                # Get exam IDs that have questions matching user's department shortname
                exam_ids_with_matching_questions = ExamQuestion.objects.filter(
                    department_shortname=user_dept_shortname
                ).values_list('exam_id', flat=True).distinct()
                
                queryset = ExamSchedule.objects.filter(
                    exam_id__in=exam_ids_with_matching_questions
                )
                scoped_queryset_set = True

        params = self.request.query_params
        search = params.get('search')
        department = params.get('department')
        semester = params.get('semester')
        date_filter = params.get('date_filter')

        if search:
            normalized_search_semester = normalize_semester_filter(search)
            search_query = (
                Q(exam__department__icontains=search)
                | Q(exam__semester__icontains=normalized_search_semester)
            )
            if str(search).isdigit():
                search_query |= Q(id=int(search)) | Q(exam_id=int(search))
            queryset = queryset.filter(search_query)
        if department:
            queryset = queryset.filter(exam__department__icontains=department)
        if semester:
            queryset = queryset.filter(exam__semester__icontains=normalize_semester_filter(semester))
        if date_filter == 'today':
            queryset = queryset.filter(start_time__date=timezone.localdate())

        return queryset.select_related('exam').prefetch_related('exam__exam_questions').order_by('start_time')


@extend_schema(
    summary="Create exam schedule",
    description="""Create a new exam schedule with exam ID and start time.
    
    The end time is automatically calculated based on the exam's duration.
    
    Example Usage:
    - Provide exam_id and start_time
    - System automatically calculates end_time using exam duration
    - If exam duration is 120 minutes and start_time is 15:00, end_time will be 17:00
    - Times should be in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
    """,
    tags=['Schedule'],
    request=CreateExamScheduleSerializer,
    examples=[
        OpenApiExample(
            'Auto-Calculate End Time',
            summary='Example request with auto-calculated end time',
            description='Provide only exam_id and start_time. End time is calculated automatically based on exam duration.',
            value={
                'exam_id': 16,
                'start_time': '2025-09-26T15:00:00Z',
                'is_active': True
            },
            request_only=True,
        ),
    ],
    responses={
        201: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Success message'},
                'schedule': {'$ref': '#/components/schemas/ExamSchedule'},
                'exam_details': {
                    'type': 'object',
                    'properties': {
                        'exam_id': {'type': 'integer'},
                        'department': {'type': 'string'},
                        'semester': {'type': 'string'},
                        'total_questions': {'type': 'integer'},
                        'present_question': {'type': 'integer'},
                        'duration_minutes': {'type': 'integer'}
                    }
                }
            },
            'example': {
                'message': 'Exam schedule created successfully (Duration: 120 minutes)',
                'schedule': {
                    'id': 1,
                    'exam': 16,
                    'start_time': '2025-09-26T15:00:00Z',
                    'end_time': '2025-09-26T17:00:00Z',
                    'is_active': True,
                    'created_at': '2025-09-26T14:30:00Z'
                },
                'exam_details': {
                    'exam_id': 16,
                    'department': 'Computer Science',
                    'semester': 'Fall 2025',
                    'total_questions': 10,
                    'present_question': 10,
                    'duration_minutes': 120
                },
                'calculated_times': {
                    'start_time': '2025-09-26T15:00:00+00:00',
                    'end_time': '2025-09-26T17:00:00+00:00',
                    'duration_minutes': 120
                }
            }
        },
        400: {
            'description': 'Bad request - validation errors',
            'content': {
                'application/json': {
                    'examples': {
                        'missing_exam_id': {
                            'summary': 'Missing exam_id',
                            'value': {'error': 'exam_id is required'}
                        },
                        'missing_times': {
                            'summary': 'Missing time fields',
                            'value': {'error': 'start_time is required'}
                        },
                        'invalid_time_format': {
                            'summary': 'Invalid time format',
                            'value': {
                                'start_time': ['Datetime has wrong format. Use one of these formats instead: YYYY-MM-DD[T]HH:MM[:ss[.uuuuuu]][+HH:MM|-HH:MM|Z].']
                            }
                        },
                        'end_before_start': {
                            'summary': 'End time before start time',
                            'value': {'non_field_errors': ['End time must be after start time']}
                        }
                    }
                }
            }
        },
        404: {
            'description': 'Exam not found',
            'content': {
                'application/json': {
                    'example': {'error': 'Exam with ID 999 not found'}
                }
            }
        }
    }
)
@csrf_exempt
@api_view(['POST'])
def create_exam_schedule(request):
    """
    Create a new exam schedule
    
    This endpoint allows you to schedule an exam by providing:
    - exam_id: The ID of an existing exam
    - start_time: When the exam should start (ISO 8601 format)
    - is_active: Whether the schedule is active (optional, defaults to True)
    
    The end_time is automatically calculated based on the exam's duration.
    
    Example request body:
    {
        "exam_id": 16,
        "start_time": "2025-09-26T15:00:00Z",
        "is_active": true
    }
    
    Time format examples:
    - "2025-09-26T15:00:00Z" (UTC time)
    - "2025-09-26T15:00:00+06:00" (Bangladesh time)
    - "2025-09-26T15:00:00" (local time)
    """
    # Validate request data using serializer (this will auto-calculate end_time)
    request_serializer = CreateExamScheduleSerializer(data=request.data)
    if not request_serializer.is_valid():
        return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = request_serializer.validated_data
    exam = validated_data['exam']  # Exam object is now available from serializer
    
    # Create schedule data for database serializer
    schedule_data = {
        'exam': exam.id,
        'start_time': validated_data['start_time'],
        'end_time': validated_data['end_time'],  # This is auto-calculated
        'is_active': validated_data.get('is_active', True)
    }
    
    # Use simple serializer for database operations (without exam details)
    from ..serializers.exam import ExamScheduleCreateSerializer
    schedule_serializer = ExamScheduleCreateSerializer(data=schedule_data)
    if schedule_serializer.is_valid():
        # Save the schedule
        schedule = schedule_serializer.save()

        # Ensure a PublishedExam entry exists for this exam (is_published=False)
        from ..models import PublishedExam
        PublishedExam.objects.get_or_create(exam=exam, defaults={"is_published": False})

        return Response({
            "message": f"Exam schedule created successfully (Duration: {exam.duration_minutes} minutes)",
            "schedule": ExamScheduleSerializer(schedule).data,
            "exam_details": {
                "exam_id": exam.id,
                "department": exam.department,
                "semester": exam.semester,
                "total_questions": exam.total_questions,
                "present_question": exam.present_question,
                "duration_minutes": exam.duration_minutes
            },
            "calculated_times": {
                "start_time": validated_data['start_time'].isoformat(),
                "end_time": validated_data['end_time'].isoformat(),
                "duration_minutes": exam.duration_minutes
            }
        }, status=status.HTTP_201_CREATED)
    
    return Response(schedule_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    summary="Schedule detail",
    description="Retrieve, update or delete a specific exam schedule",
    tags=['Schedule'],
    responses={200: ExamScheduleSerializer}
)
class ScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get specific schedule details"""
    queryset = ExamSchedule.objects.all()
    serializer_class = ExamScheduleSerializer
    lookup_url_kwarg = 'schedule_id'


@extend_schema(
    summary="Get schedules for a specific teacher",
    description="Retrieve all exam schedules assigned to a specific teacher based on StudentAssignTeacherExam assignments. Returns unique schedules with exam details.",
    tags=['Schedule'],
    responses={
        200: {
            'type': 'object',
            'properties': {
                'success': {'type': 'boolean'},
                'teacher': {
                    'type': 'object',
                    'properties': {
                        'id': {'type': 'integer'},
                        'username': {'type': 'string'},
                        'email': {'type': 'string'}
                    }
                },
                'exam_count': {'type': 'integer'},
                'viva_count': {'type': 'integer'},
                'viva_group_count': {'type': 'integer'},
                'count': {'type': 'integer'},
                'exam_schedules': {'type': 'array', 'items': {'$ref': '#/components/schemas/ExamSchedule'}},
                'viva_schedules': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'id': {'type': 'string'},
                            'scheduled_at': {'type': ['string', 'null']},
                            'time': {'type': ['string', 'null']},
                            'room': {'type': 'string'},
                            'total_marks': {'type': 'number'},
                            'exam': {'type': 'integer'},
                            'exam_name': {'type': 'string'},
                            'exam_details': {'type': 'object'},
                            'count': {'type': 'integer'},
                            'students': {'type': 'array'}
                        }
                    }
                },
                'message': {'type': 'string'}
            }
        },
        404: {
            'type': 'object',
            'properties': {
                'success': {'type': 'boolean'},
                'message': {'type': 'string'}
            }
        }
    }
)
@api_view(['GET'])
@csrf_exempt
def get_teacher_schedule(request, teacher_id):
    """
    Get all exam and viva schedules assigned to a specific teacher.
    
    This endpoint retrieves unique written exam schedules through StudentAssignTeacherExam
    and viva assignments directly from VivaAssignment.
    """
    from ..models import User, StudentAssignTeacherExam
    from ..authentication import CustomJWTAuthentication
    from rest_framework.permissions import IsAuthenticated
    
    # Authenticate the request
    authenticator = CustomJWTAuthentication()
    try:
        user_auth_tuple = authenticator.authenticate(request)
        if user_auth_tuple is None:
            return Response({
                'success': False,
                'message': 'Authentication required'
            }, status=status.HTTP_401_UNAUTHORIZED)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Authentication failed: {str(e)}'
        }, status=status.HTTP_401_UNAUTHORIZED)
    
    # Check if teacher exists
    try:
        teacher = User.objects.get(id=teacher_id)
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Teacher not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Get all unique written exam schedules assigned to this teacher
    assignments = StudentAssignTeacherExam.objects.filter(
        teacher_id=teacher_id
    ).select_related('schedule', 'schedule__exam').values_list('schedule_id', flat=True).distinct()
    
    # Get exam schedule objects with related exam questions for department shortname extraction
    exam_schedules = ExamSchedule.objects.filter(
        id__in=assignments
    ).select_related('exam').prefetch_related('exam__exam_questions').order_by('-start_time')

    # Get viva assignments for this teacher
    viva_schedules = VivaAssignment.objects.filter(
        teacher_id=teacher_id
    ).select_related('student', 'teacher', 'exam').prefetch_related('exam__exam_questions').order_by('-scheduled_at', '-updated_at', '-id')
    
    # Serialize schedules
    exam_serializer = ExamScheduleSerializer(exam_schedules, many=True)
    viva_serializer = VivaAssignmentSerializer(viva_schedules, many=True)
    viva_groups = OrderedDict()

    for viva_item in viva_serializer.data:
        group_key = viva_item.get('scheduled_at') or '__unscheduled__'
        if group_key not in viva_groups:
            viva_groups[group_key] = {
                'id': group_key,
                'scheduled_at': viva_item.get('scheduled_at'),
                'time': viva_item.get('time'),
                'room': viva_item.get('room'),
                'total_marks': viva_item.get('total_marks'),
                'exam': viva_item.get('exam'),
                'exam_name': viva_item.get('exam_name'),
                'exam_details': viva_item.get('exam_details'),
                'remarks': viva_item.get('remarks'),
                'students': [],
                'count': 0,
            }

        viva_groups[group_key]['students'].append(viva_item)
        viva_groups[group_key]['count'] += 1
    
    return Response({
        'success': True,
        'teacher': {
            'id': teacher.id,
            'username': teacher.username,
            'email': teacher.email
        },
        'exam_count': exam_schedules.count(),
        'viva_count': viva_schedules.count(),
        'viva_group_count': len(viva_groups),
        'count': exam_schedules.count() + len(viva_groups),
        'exam_schedules': exam_serializer.data,
        'viva_schedules': list(viva_groups.values()),
        'message': f'Found {exam_schedules.count()} exam schedules and {viva_schedules.count()} viva assignments for teacher {teacher.username}'
    })
