from django.shortcuts import render
from django.http import Http404
from rest_framework import generics, status, serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
import random
from .models import ScrappedQuestion, Exam, ExamQuestion, ExamSchedule, Students, Submission
from .serializers import (
    ScrappedQuestionSerializer, TotalQuestionsSerializer, ExamCreateSerializer, 
    ExamQuestionSerializer, ExamScheduleSerializer, StudentsSerializer, 
    SubmissionSerializer, ExamResultSerializer, ExamSerializer, CreateExamScheduleSerializer
)

# Create your views here.

@extend_schema(
    summary="Get all scrapped questions",
    description="Retrieve all scrapped questions with optional filtering, sorting, and pagination. Returns questions with pagination metadata.",
    parameters=[
        OpenApiParameter('subject', OpenApiTypes.STR, location=OpenApiParameter.QUERY, description='Filter questions by subject'),
        OpenApiParameter('type', OpenApiTypes.STR, location=OpenApiParameter.QUERY, enum=['option','text'], description='Filter questions by type'),
        OpenApiParameter('semester', OpenApiTypes.STR, location=OpenApiParameter.QUERY, description='Filter questions by semester'),
        OpenApiParameter('search', OpenApiTypes.STR, location=OpenApiParameter.QUERY, description='Search in question text and subject'),
        OpenApiParameter('sort_by', OpenApiTypes.STR, location=OpenApiParameter.QUERY, enum=['id','subject','type','marks','semester','-id','-subject','-type','-marks','-semester'], description='Sort questions by field'),
        OpenApiParameter('page', OpenApiTypes.INT, location=OpenApiParameter.QUERY, description='Page number (default 1)'),
        OpenApiParameter('per_page', OpenApiTypes.INT, location=OpenApiParameter.QUERY, description='Items per page (default 10, max 100)'),
    ],
    tags=['Questions'],
)
class AllScrappedQuestionsView(generics.ListAPIView):
    queryset = ScrappedQuestion.objects.all()
    serializer_class = ScrappedQuestionSerializer

    def get_queryset(self):
        queryset = ScrappedQuestion.objects.all()
        params = self.request.query_params

        # Filters
        if subject := params.get('subject'):
            queryset = queryset.filter(subject__icontains=subject)
        if question_type := params.get('type'):
            queryset = queryset.filter(type=question_type)
        if semester := params.get('semester'):
            queryset = queryset.filter(semester__icontains=semester)
        if search := params.get('search'):
            queryset = queryset.filter(Q(questions__icontains=search) | Q(subject__icontains=search))

        # Sorting
        sort_by = params.get('sort_by', 'id')
        valid_sort_fields = ['id', 'subject', 'type', 'marks', 'semester',
                           '-id', '-subject', '-type', '-marks', '-semester']
        if sort_by not in valid_sort_fields:
            sort_by = 'id'
        queryset = queryset.order_by(sort_by)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        params = request.query_params

        # Pagination
        page = max(int(params.get('page', 1)), 1)
        per_page = min(int(params.get('per_page', 10)), 100)
        total_questions = queryset.count()
        total_pages = max((total_questions + per_page - 1) // per_page, 1)

        # Correct page if out of bounds
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page
        paginated_queryset = queryset[offset:offset + per_page]
        serializer = self.get_serializer(paginated_queryset, many=True)

        # Pagination metadata
        pagination_data = {
            'current_page': page,
            'per_page': per_page,
            'total_questions': total_questions,
            'total_pages': total_pages,
            'has_next': page < total_pages,
            'has_previous': page > 1,
            'next_page': page + 1 if page < total_pages else None,
            'previous_page': page - 1 if page > 1 else None,
        }

        # Filters applied
        filters_applied = {k: v for k, v in {
            'subject': params.get('subject'),
            'type': params.get('type'),
            'semester': params.get('semester'),
            'search': params.get('search'),
            'sort_by': params.get('sort_by')
        }.items() if v is not None}

        return Response({
            'questions': serializer.data,
            'pagination': pagination_data,
            'filters': filters_applied
        })


@extend_schema(
    summary="Get questions statistics",
    description="Get comprehensive statistics about all questions including counts by subject, type, and semester.",
    tags=['Statistics'],
    responses={
        200: {
            'type': 'object',
            'properties': {
                'total_questions': {'type': 'integer', 'description': 'Total number of questions'},
                'subjects': {
                    'type': 'object',
                    'description': 'Count by subject',
                    'example': {
                        'Mathematics': 3,
                        'English': 11,
                        'Physics': 5,
                        'General Knowledge': 3,
                        'IT - Using AI and ChatGPT': 3
                    }
                },
                'types': {
                    'type': 'object',
                    'description': 'Count by question type',
                    'example': {
                        'option': 20,
                        'text': 5
                    }
                },
                'semesters': {
                    'type': 'object',
                    'description': 'Count by semester',
                    'example': {
                        'General': 25
                    }
                }
            }
        }
    }
)
@api_view(['GET'])
def questions_stats(request):
    """
    API endpoint to get statistics about questions
    """
    total_questions = ScrappedQuestion.objects.count()

    # Count by subject
    subjects = ScrappedQuestion.objects.values_list('subject', flat=True).distinct()
    subject_counts = {}
    for subject in subjects:
        subject_counts[subject] = ScrappedQuestion.objects.filter(subject=subject).count()

    # Count by type
    type_counts = {}
    for choice in ScrappedQuestion.TYPE_CHOICES:
        type_counts[choice[0]] = ScrappedQuestion.objects.filter(type=choice[0]).count()

    # Count by semester
    semesters = ScrappedQuestion.objects.values_list('semester', flat=True).distinct()
    semester_counts = {}
    for semester in semesters:
        semester_counts[semester] = ScrappedQuestion.objects.filter(semester=semester).count()

    return Response({
        'total_questions': total_questions,
        'subjects': subject_counts,
        'types': type_counts,
        'semesters': semester_counts
    })


@extend_schema(
    summary="Get total questions count by subject",
    description="Returns total number of questions and per-subject counts.",
    tags=['Statistics'],
    responses={200: TotalQuestionsSerializer}
)
@api_view(['GET'])
def total_questions(request):
    total_count = ScrappedQuestion.objects.count()

    # Build subject counts dynamically
    subjects = ScrappedQuestion.objects.values_list('subject', flat=True).distinct()
    subject_counts = {
        subject: ScrappedQuestion.objects.filter(subject=subject).count()
        for subject in subjects
    }

    result = {
        'total_questions': total_count,
        'subjects': subject_counts
    }

    return Response(result)


@extend_schema(
    summary="Create exam with questions",
    description="Create an exam by selecting questions from different subjects based on percentage distribution.",
    request=ExamCreateSerializer,
    tags=['Exam'],
    responses={
        201: {
            'type': 'object',
            'properties': {
                'exam_id': {'type': 'integer', 'description': 'Created exam ID'},
                'total_questions': {'type': 'integer', 'description': 'Total questions in exam'},
                'total_marks': {'type': 'integer', 'description': 'Total marks for exam'},
                'message': {'type': 'string', 'description': 'Success message'}
            }
        },
        400: {'description': 'Bad request - validation errors'}
    }
)
class CreateExamAPIView(APIView):

    def post(self, request):
        serializer = ExamCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        total_questions = data['total_questions']
        subject_distribution = data['subject_distribution']
        except_semesters = data.get('except_semesters', [])

        # Check percentage validity
        if sum(subject_distribution.values()) != 100:
            return Response(
                {"error": "Subject distribution percentages must sum to 100"},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            exam = Exam.objects.create(
                department=data['department'],
                semester=data['semester'],
                total_questions=total_questions,
                present_question=0,  # Initialize to 0
                total_marks=0,  # Will be calculated after adding questions
                duration_minutes=data['duration_minutes'],
                except_semesters=except_semesters,
            )

            selected_questions = []
            for subject, percent in subject_distribution.items():
                num_questions = round(total_questions * (percent / 100))

                # Filter questions for this subject
                qs = ScrappedQuestion.objects.filter(subject__iexact=subject)
                if except_semesters:
                    qs = qs.exclude(semester__in=except_semesters)

                available_count = qs.count()
                if available_count < num_questions:
                    transaction.set_rollback(True)
                    return Response(
                        {"error": f"Not enough questions for {subject}. Needed {num_questions}, available {available_count}."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Random unique sample
                picked = random.sample(list(qs), num_questions)
                selected_questions.extend(picked)

            # Save selected questions into ExamQuestion
            total_marks = 0
            for q in selected_questions:
                ExamQuestion.objects.create(
                    exam=exam,
                    subject=q.subject,
                    question_text=q.questions,
                    type=q.type,
                    text=q.text,
                    options=q.options,
                    answer=q.answer,
                    marks=q.marks
                )
                total_marks += q.marks

            # Update exam with actual counts
            exam.present_question = len(selected_questions)
            exam.total_marks = total_marks
            exam.save()

            return Response({
                "exam_id": exam.id,
                "total_questions": len(selected_questions),
                "total_marks": total_marks,
                "message": "Exam created successfully"
            },
            status=status.HTTP_201_CREATED
        )


# List all exams
@extend_schema(
    summary="Get all exams",
    description="Retrieve all exams with their details including current question count",
    tags=['Exam'],
    responses={200: ExamSerializer(many=True)}
)
class AllExamsView(generics.ListAPIView):
    """List all exams in the system"""
    queryset = Exam.objects.all().order_by('-created_at')
    serializer_class = ExamSerializer


# List all questions of a specific exam
@extend_schema(
    summary="Get all questions in an exam",
    description="Retrieve all questions that belong to a specific exam",
    tags=['Exam'],
    responses={200: ExamQuestionSerializer(many=True)}
)
class ExamQuestionListView(generics.ListAPIView):
    serializer_class = ExamQuestionSerializer

    def get_queryset(self):
        exam_id = self.kwargs['exam_id']
        return ExamQuestion.objects.filter(exam_id=exam_id)


# Add individual question to an exam
@extend_schema(
    summary="Add individual question to exam",
    description="Add a single question to a specific exam. Validates that present_question count doesn't exceed total_questions limit.",
    request=ExamQuestionSerializer,
    responses={
        201: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Success message'},
                'question': {'$ref': '#/components/schemas/ExamQuestion'},
                'exam_stats': {
                    'type': 'object',
                    'properties': {
                        'present_question': {'type': 'integer'},
                        'total_questions': {'type': 'integer'},
                        'remaining_slots': {'type': 'integer'}
                    }
                }
            }
        },
        400: {'description': 'Bad request - validation errors or exam full'},
        404: {'description': 'Exam not found'}
    },
    tags=['Exam']
)
class AddQuestionToExamView(generics.CreateAPIView):
    serializer_class = ExamQuestionSerializer

    def create(self, request, exam_id):
        """Add individual question to an exam with proper validation using present_question field"""
        try:
            exam = Exam.objects.get(id=exam_id)
        except Exam.DoesNotExist:
            return Response(
                {"error": "Exam not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check if exam has reached its question limit
        if exam.present_question >= exam.total_questions:
            return Response(
                {
                    "error": f"Cannot add more questions. Exam already has {exam.present_question}/{exam.total_questions} questions."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create serializer with request data
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # Use transaction to ensure data consistency
            with transaction.atomic():
                # Save the question with the exam reference
                question = serializer.save(exam=exam)

                # Update present_question count
                exam.present_question += 1
                exam.save()

                return Response(
                    {
                        "message": "Question added successfully",
                        "question": ExamQuestionSerializer(question).data,
                        "exam_stats": {
                            "present_question": exam.present_question,
                            "total_questions": exam.total_questions,
                            "remaining_slots": exam.total_questions - exam.present_question
                        }
                    },
                    status=status.HTTP_201_CREATED
                )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Edit specific question in an exam
@extend_schema(
    summary="Edit or delete specific question in an exam",
    description="Update or delete a specific question within an exam. Use PUT to update question details or DELETE to remove the question from the exam.",
    tags=['Exam'],
    request=ExamQuestionSerializer,
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Success message'},
                'question': {'$ref': '#/components/schemas/ExamQuestion'}
            }
        },
        404: {'description': 'Question or exam not found'},
        400: {'description': 'Bad request - validation errors'}
    }
)
class ExamQuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    API endpoint to edit or delete a specific question in an exam
    Supports PUT (update) and DELETE operations
    """
    serializer_class = ExamQuestionSerializer
    lookup_url_kwarg = 'question_id'

    def get_queryset(self):
        exam_id = self.kwargs['exam_id']
        return ExamQuestion.objects.filter(exam_id=exam_id)

    def get_object(self):
        """
        Get the specific exam question
        """
        exam_id = self.kwargs['exam_id']
        question_id = self.kwargs['question_id']

        try:
            # Ensure the exam exists
            exam = Exam.objects.get(id=exam_id)
            # Get the specific question
            exam_question = ExamQuestion.objects.get(id=question_id, exam=exam)
            return exam_question
        except Exam.DoesNotExist:
            raise Http404("Exam not found")
        except ExamQuestion.DoesNotExist:
            raise Http404("Question not found in this exam")

    def put(self, request, *args, **kwargs):
        """
        Update a specific question in the exam
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        # Update the question
        updated_question = serializer.save()

        return Response({
            'message': 'Question updated successfully',
            'question': ExamQuestionSerializer(updated_question).data
        }, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        """
        Delete a specific question from the exam
        """
        instance = self.get_object()
        exam = instance.exam

        # Use transaction to ensure data consistency
        with transaction.atomic():
            # Delete the question
            instance.delete()

            # Update present_question count (decrease by 1)
            exam.present_question = max(0, exam.present_question - 1)

            # Update total marks count
            exam.total_marks = sum(ExamQuestion.objects.filter(exam=exam).values_list('marks', flat=True))
            exam.save()

        return Response({
            'message': 'Question deleted successfully',
            'exam_stats': {
                'present_question': exam.present_question,
                'total_questions': exam.total_questions,
                'remaining_slots': exam.total_questions - exam.present_question
            }
        }, status=status.HTTP_200_OK)


# Delete specific exam
@extend_schema(
    summary="Delete exam",
    description="Delete a specific exam and all its associated questions",
    tags=['Exam'],
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Success message'},
                'deleted_exam_id': {'type': 'integer', 'description': 'ID of deleted exam'}
            }
        },
        404: {'description': 'Exam not found'}
    }
)
class DeleteExamView(generics.DestroyAPIView):
    """Delete a specific exam"""
    queryset = Exam.objects.all()
    lookup_url_kwarg = 'exam_id'

    def destroy(self, request, *args, **kwargs):
        try:
            exam = self.get_object()
            exam_id = exam.id
            department = exam.department

            # Delete the exam (this will cascade delete all related ExamQuestion objects)
            self.perform_destroy(exam)

            return Response(
                {
                    "message": f"Exam {exam_id} for {department} department deleted successfully",
                    "deleted_exam_id": exam_id
                },
                status=status.HTTP_200_OK
            )
        except Exam.DoesNotExist:
            return Response(
                {"error": "Exam not found"},
                status=status.HTTP_404_NOT_FOUND
            )


# ================= STUDENT MANAGEMENT =================

@extend_schema(
    summary="Get all students",
    description="Retrieve all registered students",
    tags=['Students'],
    responses={200: StudentsSerializer(many=True)}
)
class AllStudentsView(generics.ListCreateAPIView):
    """List all students and create new students"""
    queryset = Students.objects.all().order_by('-created_at')
    serializer_class = StudentsSerializer


@extend_schema(
    summary="Student detail",
    description="Retrieve, update or delete a specific student",
    tags=['Students'],
    responses={200: StudentsSerializer}
)
class StudentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get specific student details"""
    queryset = Students.objects.all()
    serializer_class = StudentsSerializer
    lookup_url_kwarg = 'student_id'


# ================= EXAM SCHEDULE MANAGEMENT =================

@extend_schema(
    summary="Get all exam schedules",
    description="Retrieve all exam schedules",
    tags=['Schedule'],
    responses={200: ExamScheduleSerializer(many=True)}
)
class AllSchedulesView(generics.ListCreateAPIView):
    """List all exam schedules and create new schedules"""
    queryset = ExamSchedule.objects.all().order_by('start_time')
    serializer_class = ExamScheduleSerializer


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
    
    # Use model serializer for database operations
    schedule_serializer = ExamScheduleSerializer(data=schedule_data)
    if schedule_serializer.is_valid():
        # Save the schedule
        schedule = schedule_serializer.save()
        
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


# ================= STUDENT EXAM FUNCTIONALITY =================

@extend_schema(
    summary="Student login",
    description="""Authenticate student with username and password.
    
    This endpoint validates student credentials and returns student information upon successful authentication.
    """,
    tags=['Student App'],
    request={
        'type': 'object',
        'properties': {
            'username': {
                'type': 'string', 
                'description': 'Student username (unique identifier)',
                'example': 'john_doe'
            },
            'password': {
                'type': 'string', 
                'description': 'Student password',
                'example': 'mypassword123'
            }
        },
        'required': ['username', 'password'],
        'example': {
            'username': 'john_doe',
            'password': 'mypassword123'
        }
    },
    responses={
        200: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string', 'description': 'Success message'},
                'student': {'$ref': '#/components/schemas/Students'}
            },
            'example': {
                'message': 'Login successful',
                'student': {
                    'id': 1,
                    'username': 'john_doe',
                    'f_id': 'STU2024001',
                    'created_at': '2024-12-10T08:30:00Z'
                }
            }
        },
        400: {
            'description': 'Bad request - missing required fields',
            'content': {
                'application/json': {
                    'examples': {
                        'missing_username': {
                            'summary': 'Missing username',
                            'value': {'error': 'Username and password are required'}
                        },
                        'missing_password': {
                            'summary': 'Missing password',
                            'value': {'error': 'Username and password are required'}
                        }
                    }
                }
            }
        },
        401: {
            'description': 'Unauthorized - invalid credentials',
            'content': {
                'application/json': {
                    'example': {'error': 'Invalid username or password'}
                }
            }
        }
    }
)
@api_view(['POST'])
def student_login(request):
    """
    Student login endpoint
    
    Authenticates a student using username and password credentials.
    
    Request Body Example:
    {
        "username": "john_doe",
        "password": "mypassword123"
    }
    
    Success Response (200):
    {
        "message": "Login successful",
        "student": {
            "id": 1,
            "username": "john_doe",
            "f_id": "STU2024001",
            "created_at": "2024-12-10T08:30:00Z"
        }
    }
    
    Error Response (401):
    {
        "error": "Invalid username or password"
    }
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response(
            {"error": "Username and password are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        student = Students.objects.get(username=username, password=password)
        return Response({
            "message": "Login successful",
            "student": StudentsSerializer(student).data
        }, status=status.HTTP_200_OK)
    except Students.DoesNotExist:
        return Response(
            {"error": "Invalid username or password"},
            status=status.HTTP_401_UNAUTHORIZED
        )


@extend_schema(
    summary="Get available exams for student",
    description="Get active exams that are scheduled and available for the student",
    tags=['Student App'],
    responses={200: ExamSerializer(many=True)}
)
class StudentAvailableExamsView(generics.ListAPIView):
    """Get active exams available for students"""
    serializer_class = ExamSerializer
    
    def get_queryset(self):
        from django.utils import timezone
        current_time = timezone.now()
        
        # Get exams that have active schedules
        active_exam_ids = ExamSchedule.objects.filter(
            is_active=True,
            start_time__lte=current_time,
            end_time__gte=current_time
        ).values_list('exam_id', flat=True)
        
        return Exam.objects.filter(id__in=active_exam_ids)


@extend_schema(
    summary="Get exam questions for student",
    description="Get all questions for a specific exam (for student to take exam)",
    tags=['Student App'],
    responses={200: ExamQuestionSerializer(many=True)}
)
class StudentExamQuestionsView(generics.ListAPIView):
    """Get exam questions for student to take exam"""
    serializer_class = ExamQuestionSerializer
    
    def get_queryset(self):
        exam_id = self.kwargs['exam_id']
        return ExamQuestion.objects.filter(exam_id=exam_id).order_by('subject', 'id')


@extend_schema(
    summary="Submit exam answers",
    description="Submit student's answers for an exam",
    tags=['Student App'],
    request={
        'type': 'object',
        'properties': {
            'student_id': {'type': 'integer'},
            'submissions': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'question_id': {'type': 'integer'},
                        'answer': {'type': 'string'}
                    }
                }
            }
        }
    },
    responses={
        201: {
            'type': 'object',
            'properties': {
                'message': {'type': 'string'},
                'exam_result': {'$ref': '#/components/schemas/ExamResult'}
            }
        }
    }
)
@api_view(['POST'])
def submit_exam(request, exam_id):
    """Submit student's exam answers"""
    student_id = request.data.get('student_id')
    submissions = request.data.get('submissions', [])
    
    if not student_id:
        return Response(
            {"error": "Student ID is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not submissions:
        return Response(
            {"error": "At least one answer submission is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        student = Students.objects.get(id=student_id)
        exam = Exam.objects.get(id=exam_id)
    except (Students.DoesNotExist, Exam.DoesNotExist):
        return Response(
            {"error": "Student or Exam not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Process submissions
    with transaction.atomic():
        submission_results = []
        
        for submission_data in submissions:
            question_id = submission_data.get('question_id')
            answer = submission_data.get('answer', '').strip()
            
            try:
                question = ExamQuestion.objects.get(id=question_id, exam=exam)
                
                # Check if answer is correct
                is_correct = False
                if question.type == 'option':
                    # For option type, compare with correct answer
                    correct_answers = question.answer if isinstance(question.answer, list) else [question.answer]
                    is_correct = answer in correct_answers
                elif question.type == 'text':
                    # For text type, simple string comparison (can be enhanced)
                    is_correct = answer.lower() == str(question.answer).lower()
                
                # Create or update submission
                submission, created = Submission.objects.update_or_create(
                    student=student,
                    exam=exam,
                    question=question,
                    defaults={
                        'answer': answer,
                        'is_correct': is_correct
                    }
                )
                
                submission_results.append({
                    'question_id': question_id,
                    'is_correct': is_correct,
                    'marks_obtained': question.marks if is_correct else 0
                })
                
            except ExamQuestion.DoesNotExist:
                continue
    
    # Calculate results
    result = calculate_exam_result(student_id, exam_id)
    
    return Response({
        "message": "Exam submitted successfully",
        "submission_results": submission_results,
        "exam_result": result
    }, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="Get exam result",
    description="Get detailed exam result for a student",
    tags=['Student App'],
    responses={200: ExamResultSerializer}
)
@api_view(['GET'])
def get_exam_result(request, exam_id, student_id):
    """Get exam result for a specific student and exam"""
    try:
        student = Students.objects.get(id=student_id)
        exam = Exam.objects.get(id=exam_id)
    except (Students.DoesNotExist, Exam.DoesNotExist):
        return Response(
            {"error": "Student or Exam not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    result = calculate_exam_result(student_id, exam_id)
    
    if not result:
        return Response(
            {"error": "No submissions found for this exam"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    return Response(result, status=status.HTTP_200_OK)


def calculate_exam_result(student_id, exam_id):
    """Helper function to calculate exam result"""
    try:
        student = Students.objects.get(id=student_id)
        exam = Exam.objects.get(id=exam_id)
        
        # Get all submissions for this student and exam
        submissions = Submission.objects.filter(student=student, exam=exam)
        
        if not submissions.exists():
            return None
        
        # Calculate overall stats
        total_questions = ExamQuestion.objects.filter(exam=exam).count()
        answered_questions = submissions.count()
        correct_answers = submissions.filter(is_correct=True).count()
        
        # Calculate marks
        total_marks = sum(ExamQuestion.objects.filter(exam=exam).values_list('marks', flat=True))
        obtained_marks = sum(s.question.marks for s in submissions if s.is_correct)
        percentage = (obtained_marks / total_marks * 100) if total_marks > 0 else 0
        
        # Calculate subject-wise results
        subject_wise = {}
        for submission in submissions:
            subject = submission.question.subject
            if subject not in subject_wise:
                subject_wise[subject] = {
                    'total_questions': 0,
                    'answered': 0,
                    'correct': 0,
                    'total_marks': 0,
                    'obtained_marks': 0
                }
            
            subject_wise[subject]['answered'] += 1
            if submission.is_correct:
                subject_wise[subject]['correct'] += 1
                subject_wise[subject]['obtained_marks'] += submission.question.marks
        
        # Add total questions and marks per subject
        for question in ExamQuestion.objects.filter(exam=exam):
            subject = question.subject
            if subject in subject_wise:
                subject_wise[subject]['total_questions'] += 1
                subject_wise[subject]['total_marks'] += question.marks
        
        return {
            'exam_id': exam_id,
            'student_id': student_id,
            'student_username': student.username,
            'total_questions': total_questions,
            'answered_questions': answered_questions,
            'correct_answers': correct_answers,
            'total_marks': total_marks,
            'obtained_marks': obtained_marks,
            'percentage': round(percentage, 2),
            'subject_wise_results': subject_wise
        }
        
    except (Students.DoesNotExist, Exam.DoesNotExist):
        return None