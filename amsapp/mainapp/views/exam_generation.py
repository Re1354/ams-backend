from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse
import random

from ..models import ScrappedQuestion, Exam, ExamQuestion, BlocklistQuestion, Department
from ..authentication import CustomJWTAuthentication
from ..serializers.exam_generation import (
    ExamGenerationRequestSerializer, ExamSaveRequestSerializer,
    GeneratedExamResponseSerializer, GeneratedQuestionSerializer
)
import json


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
@authentication_classes([CustomJWTAuthentication])
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

    # Transform serialized questions according to requested language and attach department_shortname
    raw_questions = questions_serializer.data
    transformed_questions = []
    req_language = data.get('language', 'english')
    for q in raw_questions:
        # Work on a copy to avoid mutating serializer output
        item = dict(q)

        # Ensure department_shortname is set from Department lookup
        try:
            item['department_shortname'] = department.department_shortname
        except Exception:
            # fallback to existing value or empty
            item['department_shortname'] = item.get('department_shortname', '')

        # Normalize questions/options/answer based on language
        # If language == 'english' => return english-only values
        # If language == 'both' => return only the 'both' sub-values (not the full dict)
        lang = (req_language or '').lower()
        qfield = item.get('questions')
        ofield = item.get('options')
        afield = item.get('answer')

        if lang == 'english':
            # questions field might be a dict with 'english'/'both'
            if isinstance(qfield, dict):
                item['questions'] = qfield.get('english', qfield)

            if isinstance(ofield, dict):
                # options may be {'both': {...}, 'english': {...}}
                item['options'] = ofield.get('english', ofield)

            if isinstance(afield, dict):
                item['answer'] = afield.get('english', afield)

        elif lang == 'both':
            # For 'both' requests, return only the 'both' subfields
            if isinstance(qfield, dict):
                item['questions'] = qfield.get('both', qfield)

            if isinstance(ofield, dict):
                item['options'] = ofield.get('both', ofield)

            if isinstance(afield, dict):
                item['answer'] = afield.get('both', afield)
        transformed_questions.append(item)

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
        'questions': transformed_questions
    }
    
    return Response({
        'success': True,
        'message': 'Exam questions generated successfully',
        'data': response_data
    })


@extend_schema(
    operation_id='save_generated_exam',
    tags=['Exam Generation'],
    summary="Save exam with questions",
    description="Save exam data and questions directly to database. Creates exam record and associated exam questions.",
    request=ExamSaveRequestSerializer,
    responses={
        201: OpenApiResponse(description="Exam saved successfully"),
        400: OpenApiResponse(description="Invalid request data")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def save_generated_exam(request):
    """Save exam with questions to database"""
    
    serializer = ExamSaveRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    validated_data = serializer.validated_data
    
    try:
        with transaction.atomic():
            # Create exam with all fields matching the Exam model
            exam = Exam.objects.create(
                department=validated_data['department'],
                semester=validated_data['semester'],
                total_questions=validated_data['total_questions'],
                present_question=validated_data['total_questions'],  # Set to same as total_questions
                total_marks=validated_data['total_marks'],
                duration_minutes=validated_data['duration_minutes'],
                except_semesters=validated_data.get('except_semesters', []),
                language=validated_data.get('language', 'English'),
                faculty=validated_data.get('faculty', '')
            )
            
            # Create exam questions
            for question_data in validated_data['questions']:
                # Handle question text which may be a string or a dict containing 'english'/'both'
                q_field = question_data.get('questions')
                req_lang = validated_data.get('language', 'English')
                qtext = ''
                if isinstance(q_field, dict):
                    if req_lang and str(req_lang).lower() == 'english':
                        qtext = q_field.get('english') or q_field.get('both') or json.dumps(q_field, ensure_ascii=False)
                    elif req_lang and str(req_lang).lower() == 'both':
                        # store the 'both' text as the snapshot (string)
                        qtext = q_field.get('both') or q_field.get('english') or json.dumps(q_field, ensure_ascii=False)
                    else:
                        # default: prefer english then both
                        qtext = q_field.get('english') or q_field.get('both') or json.dumps(q_field, ensure_ascii=False)
                else:
                    qtext = str(q_field or '')

                # Options can be JSON/dict and stored as-is
                options_value = question_data.get('options')

                # Answer may be a list, dict or string. Store as JSON string if list/dict, else as string
                answer_value = question_data.get('answer', '')
                if isinstance(answer_value, (list, dict)):
                    answer_stored = json.dumps(answer_value, ensure_ascii=False)
                elif answer_value is None:
                    answer_stored = ''
                else:
                    answer_stored = str(answer_value)

                # semester and department_shortname
                semester_val = question_data.get('semester') or validated_data.get('semester', '')
                dept_sn = question_data.get('department_shortname') or validated_data.get('department', '') or 'CSE'

                ExamQuestion.objects.create(
                    exam=exam,
                    subject=question_data['subject'],
                    question_text=qtext,
                    type=question_data['type'],
                    text=question_data.get('text', ''),
                    options=options_value,
                    answer=answer_stored,
                    marks=question_data.get('marks', 1),
                    semester=semester_val,
                    department_shortname=dept_sn
                )
            
            return Response({
                'success': True,
                'message': 'Exam saved successfully',
                'data': {
                    'exam_id': exam.id,
                    'department': exam.department,
                    'semester': exam.semester,
                    'total_questions': exam.total_questions,
                    'total_marks': exam.total_marks,
                    'duration_minutes': exam.duration_minutes,
                    'language': exam.language,
                    'faculty': exam.faculty,
                    'created_at': exam.created_at
                }
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error saving exam: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)








