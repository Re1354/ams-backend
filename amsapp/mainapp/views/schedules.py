from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema, OpenApiExample

from ..models import Exam, ExamSchedule
from ..serializers import ExamScheduleSerializer, CreateExamScheduleSerializer
from ..authentication import CustomJWTAuthentication


@extend_schema(
    summary="Get all exam schedules with exam details",
    description="Retrieve exam schedules with detailed exam information. Role-based filtering: superadmin sees all schedules, other users only see schedules for exams matching their department_shortname.",
    tags=['Schedule'],
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
        if hasattr(user, 'custom_user'):
            custom_user = user.custom_user
            
            # Check if user has a role
            if custom_user.role:
                role_name = custom_user.role.role_name.lower()
                
                # Check if superadmin - return all schedules
                if role_name == 'superadmin':
                    return ExamSchedule.objects.all().select_related('exam').prefetch_related('exam__exam_questions').order_by('start_time')
            
            # For non-superadmin users, filter by department_shortname
            if custom_user.department:
                from ..models import ExamQuestion
                user_dept_shortname = custom_user.department.department_shortname
                
                # Get exam IDs that have questions matching user's department shortname
                exam_ids_with_matching_questions = ExamQuestion.objects.filter(
                    department_shortname=user_dept_shortname
                ).values_list('exam_id', flat=True).distinct()
                
                return ExamSchedule.objects.filter(
                    exam_id__in=exam_ids_with_matching_questions
                ).select_related('exam').prefetch_related('exam__exam_questions').order_by('start_time')
            
            # If user has no department assigned, return empty queryset
            return ExamSchedule.objects.none()
        
        # If no custom_user, return empty queryset for security
        return ExamSchedule.objects.none()


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
                'count': {'type': 'integer'},
                'schedules': {'type': 'array', 'items': {'$ref': '#/components/schemas/ExamSchedule'}},
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
    Get all exam schedules assigned to a specific teacher.
    
    This endpoint retrieves all unique schedules where the teacher has been assigned
    students through the StudentAssignTeacherExam model.
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
    
    # Get all unique schedules assigned to this teacher
    assignments = StudentAssignTeacherExam.objects.filter(
        teacher_id=teacher_id
    ).select_related('schedule', 'schedule__exam').values_list('schedule_id', flat=True).distinct()
    
    # Get schedule objects
    schedules = ExamSchedule.objects.filter(
        id__in=assignments
    ).select_related('exam').order_by('-start_time')
    
    # Serialize schedules
    serializer = ExamScheduleSerializer(schedules, many=True)
    
    return Response({
        'success': True,
        'teacher': {
            'id': teacher.id,
            'username': teacher.username,
            'email': teacher.email
        },
        'count': schedules.count(),
        'schedules': serializer.data,
        'message': f'Found {schedules.count()} schedules for teacher {teacher.username}'
    })