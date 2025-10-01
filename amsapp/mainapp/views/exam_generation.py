from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse
import random

from ..models import ScrappedQuestion, Exam, ExamQuestion, BlocklistQuestion, Department
from ..serializers.exam_generation import (
    ExamGenerationRequestSerializer, ExamSaveRequestSerializer,
    GeneratedExamResponseSerializer, GeneratedQuestionSerializer,
    BlocklistQuestionSerializer, BlockQuestionRequestSerializer, 
    UnblockQuestionRequestSerializer
)


@extend_schema(
    operation_id='generate_exam',
    tags=['Exam Generation'],
    summary="Generate exam questions",
    description="Generate exam questions based on subjects and marks. Questions are not saved until explicitly requested.",
    request=ExamGenerationRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=GeneratedExamResponseSerializer,
            description="Exam questions generated successfully"
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Not enough questions available")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_exam(request):
    """Generate exam questions without saving"""
    
    serializer = ExamGenerationRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    # Validate department exists
    try:
        department = Department.objects.get(id=data['department_id'])
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    exclude_questions = data.get('exclude_questions', [])
    generated_questions = []
    subjects_info = []
    total_marks = 0
    
    for subject_data in data['subjects']:
        subject = subject_data['subject']
        required_marks = subject_data['marks']
        total_marks += required_marks
        
        # Get blocked question IDs for this subject
        blocked_question_ids = BlocklistQuestion.objects.filter(
            subject=subject,
            issue_solved=False
        ).values_list('original_question_id', flat=True)
        
        # Query available questions for this subject, excluding blocked and explicitly excluded ones
        all_excluded = list(exclude_questions) + list(blocked_question_ids)
        available_questions = ScrappedQuestion.objects.filter(
            subject=subject
        ).exclude(id__in=all_excluded)
        
        if not available_questions.exists():
            return Response({
                'success': False,
                'message': f'No questions available for subject: {subject}'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Select questions to meet the required marks
        selected_questions = []
        current_marks = 0
        available_list = list(available_questions)
        random.shuffle(available_list)
        
        for question in available_list:
            if current_marks < required_marks:
                selected_questions.append(question)
                current_marks += question.marks
                if current_marks >= required_marks:
                    break
        
        if current_marks < required_marks:
            return Response({
                'success': False,
                'message': f'Not enough questions to meet {required_marks} marks for {subject}. Only {current_marks} marks available.'
            }, status=status.HTTP_404_NOT_FOUND)
        
        generated_questions.extend(selected_questions)
        subjects_info.append({
            'subject': subject,
            'required_marks': required_marks,
            'actual_marks': current_marks,
            'question_count': len(selected_questions)
        })
    
    # Serialize the questions properly
    questions_serializer = GeneratedQuestionSerializer(generated_questions, many=True)
    
    # Prepare response data
    response_data = {
        'exam_id': None,  # Not saved yet
        'department_id': data['department_id'],
        'semester': data['semester'],
        'duration_minutes': data['duration_minutes'],
        'language': data['language'],
        'faculty': data['faculty'],
        'total_marks': total_marks,
        'subjects': subjects_info,
        'questions': questions_serializer.data
    }
    
    return Response({
        'success': True,
        'message': 'Exam questions generated successfully',
        'data': response_data
    })


@extend_schema(
    operation_id='save_generated_exam',
    tags=['Exam Generation'],
    summary="Save generated exam",
    description="Save previously generated exam questions to database",
    request=ExamSaveRequestSerializer,
    responses={
        201: OpenApiResponse(description="Exam saved successfully"),
        400: OpenApiResponse(description="Invalid request data")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def save_generated_exam(request):
    """Save generated exam to database"""
    
    serializer = ExamSaveRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    if not serializer.validated_data['save']:
        return Response({
            'success': False,
            'message': 'Save flag not set to true'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    exam_data = serializer.validated_data['exam_data']
    
    try:
        with transaction.atomic():
            # Create exam
            department = Department.objects.get(id=exam_data['department_id'])
            exam = Exam.objects.create(
                department=department.department_name,
                semester=exam_data['semester'],
                total_questions=len(exam_data['questions']),
                present_question=len(exam_data['questions']),
                total_marks=exam_data['total_marks'],
                duration_minutes=exam_data['duration_minutes'],
                language=exam_data['language'],
                faculty=exam_data['faculty']
            )
            
            # Create exam questions
            for question_data in exam_data['questions']:
                # Get the actual question from database
                scrapped_question = ScrappedQuestion.objects.get(id=question_data['id'])
                
                ExamQuestion.objects.create(
                    exam=exam,
                    subject=scrapped_question.subject,
                    question_text=scrapped_question.questions,
                    type=scrapped_question.type,
                    text=scrapped_question.text,
                    options=scrapped_question.options,
                    answer=scrapped_question.answer,
                    marks=scrapped_question.marks,
                    department_shortname=scrapped_question.department_shortname
                )
            
            return Response({
                'success': True,
                'message': 'Exam saved successfully',
                'data': {
                    'exam_id': exam.id,
                    'total_questions': exam.total_questions,
                    'total_marks': exam.total_marks
                }
            }, status=status.HTTP_201_CREATED)
            
    except Department.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Department not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except ScrappedQuestion.DoesNotExist:
        return Response({
            'success': False,
            'message': 'One or more questions not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error saving exam: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    operation_id='block_question',
    tags=['Question Management'],
    summary="Block a question",
    description="Move a question from scrapped_questions to blocklist_questions with remarks",
    request=BlockQuestionRequestSerializer,
    responses={
        200: OpenApiResponse(description="Question blocked successfully"),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Question not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def block_question(request):
    """Block a question by moving it to blocklist"""
    
    serializer = BlockQuestionRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    question_id = serializer.validated_data['question_id']
    remarks = serializer.validated_data['remarks']
    
    try:
        with transaction.atomic():
            # Get the question
            question = ScrappedQuestion.objects.get(id=question_id)
            
            # Create blocklist entry
            BlocklistQuestion.objects.create(
                subject=question.subject,
                questions=question.questions,
                type=question.type,
                text=question.text,
                options=question.options,
                answer=question.answer,
                marks=question.marks,
                semester=question.semester,
                department_shortname=question.department_shortname,
                original_question_id=question.id,
                remarks=remarks,
                creator=request.user,
                issue_solved=False
            )
            
            # Delete from scrapped questions
            question.delete()
            
            return Response({
                'success': True,
                'message': 'Question blocked successfully'
            })
            
    except ScrappedQuestion.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Question not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='unblock_question',
    tags=['Question Management'],
    summary="Unblock a question",
    description="Move a question back from blocklist_questions to scrapped_questions",
    request=UnblockQuestionRequestSerializer,
    responses={
        200: OpenApiResponse(description="Question unblocked successfully"),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="Blocklist entry not found")
    }
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def unblock_question(request):
    """Unblock a question by moving it back to scrapped questions"""
    
    serializer = UnblockQuestionRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    blocklist_id = serializer.validated_data['blocklist_id']
    
    try:
        with transaction.atomic():
            # Get the blocklist entry
            blocked_question = BlocklistQuestion.objects.get(id=blocklist_id)
            
            # Create new scrapped question
            ScrappedQuestion.objects.create(
                subject=blocked_question.subject,
                questions=blocked_question.questions,
                type=blocked_question.type,
                text=blocked_question.text,
                options=blocked_question.options,
                answer=blocked_question.answer,
                marks=blocked_question.marks,
                semester=blocked_question.semester,
                department_shortname=blocked_question.department_shortname
            )
            
            # Update blocklist entry to mark as solved (but keep the record)
            blocked_question.issue_solved = True
            blocked_question.save()
            
            return Response({
                'success': True,
                'message': 'Question unblocked successfully'
            })
            
    except BlocklistQuestion.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Blocklist entry not found'
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    operation_id='get_blocked_questions',
    tags=['Question Management'],
    summary="Get all blocked questions",
    description="Retrieve all questions in the blocklist",
    responses={
        200: OpenApiResponse(
            response=BlocklistQuestionSerializer(many=True),
            description="Blocked questions retrieved successfully"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_blocked_questions(request):
    """Get all blocked questions"""
    
    blocked_questions = BlocklistQuestion.objects.select_related('creator').all().order_by('-created_at')
    serializer = BlocklistQuestionSerializer(blocked_questions, many=True)
    
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Blocked questions retrieved successfully'
    })