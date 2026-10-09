from django.http import Http404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, OpenApiParameter
import random

from ..models import ScrappedQuestion, Exam, ExamQuestion
from ..serializers import (
    ExamCreateSerializer, ExamQuestionSerializer, ExamSerializer
)
from ..authentication import CustomJWTAuthentication
from ..utils import normalize_semester_filter, normalize_semester_value


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
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

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

        from ..services.access_control import get_user_access_scope
        from ..models import Department
        
        user = getattr(request.user, 'custom_user', None)
        scope = get_user_access_scope(user)
        
        if not scope['is_global']:
            dept = Department.objects.filter(
                Q(department_name__iexact=data['department']) | Q(department_shortname__iexact=data['department'])
            ).first()
            if not dept or dept.id not in scope['department_ids']:
                return Response(
                    {"error": "You do not have access to create an exam for this department."},
                    status=status.HTTP_403_FORBIDDEN
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
                    marks=q.marks,
                    semester=normalize_semester_value(q.semester, allow_blank=True),
                    department_shortname=q.department_shortname,
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


@extend_schema(
    summary="Get all exams",
    description="Retrieve exams with role-based filtering: superadmin sees all exams, other users only see exams that contain questions matching their department_shortname.",
    tags=['Exam'],
    parameters=[
        OpenApiParameter(name='search', description='Search by exam ID, department, or semester', required=False, type=str),
        OpenApiParameter(name='department', description='Filter by exam department', required=False, type=str),
        OpenApiParameter(name='semester', description='Filter by exam semester', required=False, type=str),
        OpenApiParameter(name='date_filter', description='Use today to show exams created today', required=False, type=str),
        OpenApiParameter(name='page', description='Page number', required=False, type=int),
        OpenApiParameter(name='page_size', description='Rows per page', required=False, type=int),
    ],
    responses={200: ExamSerializer(many=True)}
)
class AllExamsView(generics.ListAPIView):
    """List all exams in the system with role-based filtering"""
    serializer_class = ExamSerializer
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filter exams based on user access scope:
        - Global: All exams
        - Others: Only exams that have questions matching their permitted departments
        """
        user = self.request.user
        custom_user = user.custom_user if hasattr(user, 'custom_user') else None
        
        from ..services.access_control import get_user_access_scope
        from ..models import Department, ExamQuestion
        
        scope = get_user_access_scope(custom_user)
        
        if scope['is_global']:
            queryset = Exam.objects.all()
        else:
            if not scope['department_ids']:
                queryset = Exam.objects.none()
            else:
                valid_depts = Department.objects.filter(id__in=scope['department_ids'])
                dept_shortnames = [d.department_shortname for d in valid_depts]
                
                # Get exams that have questions matching permitted department shortnames
                exam_ids_with_matching_questions = ExamQuestion.objects.filter(
                    department_shortname__in=dept_shortnames
                ).values_list('exam_id', flat=True).distinct()
                
                # Also include exams whose primary department string matches (fallback)
                q_objs = Q(id__in=exam_ids_with_matching_questions)
                for dept in valid_depts:
                    q_objs |= Q(department__iexact=dept.department_name) | Q(department__iexact=dept.department_shortname)
                
                queryset = Exam.objects.filter(q_objs).distinct()


        params = self.request.query_params
        search = params.get('search')
        department = params.get('department')
        semester = params.get('semester')
        date_filter = params.get('date_filter')

        if search:
            normalized_search_semester = normalize_semester_filter(search)
            search_query = (
                Q(department__icontains=search)
                | Q(semester__icontains=normalized_search_semester)
            )
            if str(search).isdigit():
                search_query |= Q(id=int(search))
            queryset = queryset.filter(search_query)
        if department:
            queryset = queryset.filter(department__icontains=department)
        if semester:
            queryset = queryset.filter(semester__icontains=normalize_semester_filter(semester))
        if date_filter == 'today':
            queryset = queryset.filter(created_at__date=timezone.localdate())

        return queryset.order_by('-created_at')


@extend_schema(
    summary="Get all questions in an exam",
    description="Retrieve all questions that belong to a specific exam",
    tags=['Exam'],
    responses={200: ExamQuestionSerializer(many=True)}
)
class ExamQuestionListView(generics.ListAPIView):
    serializer_class = ExamQuestionSerializer
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        exam_id = self.kwargs['exam_id']
        return ExamQuestion.objects.filter(exam_id=exam_id)


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
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

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
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

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
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

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
