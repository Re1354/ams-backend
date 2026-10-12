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
    GeneratedExamResponseSerializer, GeneratedQuestionSerializer,
    RegenerateQuestionRequestSerializer,
)
import json


def normalize_question_text(value):
    if isinstance(value, dict):
        candidates = [
            value.get('english'),
            value.get('both'),
            *[item for item in value.values() if isinstance(item, str)],
        ]
        value = next((item for item in candidates if item), value)
    elif isinstance(value, list):
        value = ' '.join(str(item) for item in value)

    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)

    return ' '.join(value.lower().split())


def transform_generated_question(question_data, department, language):
    item = dict(question_data)
    item['department_shortname'] = getattr(
        department,
        'department_shortname',
        item.get('department_shortname', ''),
    )

    lang = (language or '').lower()
    qfield = item.get('questions')
    ofield = item.get('options')
    afield = item.get('answer')

    if lang == 'english':
        if isinstance(qfield, dict):
            item['questions'] = qfield.get('english', qfield)
        if isinstance(ofield, dict):
            item['options'] = ofield.get('english', ofield)
        if isinstance(afield, dict):
            item['answer'] = afield.get('english', afield)
    elif lang == 'both':
        if isinstance(qfield, dict):
            item['questions'] = qfield.get('both', qfield)
        if isinstance(ofield, dict):
            item['options'] = ofield.get('both', ofield)
        if isinstance(afield, dict):
            item['answer'] = afield.get('both', afield)

    return item


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
    
    exam_type = data.get('exam_type', 'SCHEDULED')
    department = None
    faculty_obj = None

    if data.get('faculty_id'):
        from ..models import Faculty
        faculty_obj = Faculty.objects.filter(id=data['faculty_id']).first()

    if data.get('department_id'):
        try:
            department = Department.objects.get(id=data['department_id'])
        except Department.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Department not found'
            }, status=status.HTTP_404_NOT_FOUND)
    elif exam_type == 'CENTRAL':
        # For central exam without department_id, pick the first department in the faculty or fallback dummy
        if faculty_obj:
            from ..models import FacultyDepartment
            fd = FacultyDepartment.objects.filter(faculty=faculty_obj).select_related('department').first()
            if fd:
                department = fd.department
        if not department:
            department = Department.objects.first()
    else:
        return Response({
            'success': False,
            'message': 'Department ID is required for scheduled exams'
        }, status=status.HTTP_400_BAD_REQUEST)
    
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

    raw_questions = questions_serializer.data
    req_language = data.get('language', 'english')
    transformed_questions = [
        transform_generated_question(q, department, req_language)
        for q in raw_questions
    ]

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
    operation_id='regenerate_exam_question',
    tags=['Exam Generation'],
    summary="Regenerate one draft exam question",
    description=(
        "Return one unsaved replacement question from the same subject and marks, "
        "excluding the current draft's question IDs and question texts."
    ),
    request=RegenerateQuestionRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=GeneratedQuestionSerializer,
            description="Replacement question generated successfully",
        ),
        400: OpenApiResponse(description="Invalid request data"),
        404: OpenApiResponse(description="No replacement question available"),
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def regenerate_question(request):
    """Return one replacement question for an unsaved generated exam draft."""

    serializer = RegenerateQuestionRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data

    department = None
    if data.get('department_id'):
        try:
            department = Department.objects.get(id=data['department_id'])
        except Department.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Department not found',
            }, status=status.HTTP_404_NOT_FOUND)
    if not department:
        department = Department.objects.first()

    blocked_question_ids = BlocklistQuestion.objects.filter(
        subject=data['subject'],
        issue_solved=False,
    ).values_list('original_question_id', flat=True)

    excluded_ids = set(data.get('exclude_question_ids', []))
    excluded_ids.update(blocked_question_ids)
    excluded_texts = {
        normalize_question_text(text)
        for text in data.get('exclude_question_texts', [])
        if normalize_question_text(text)
    }

    candidates = list(
        ScrappedQuestion.objects.filter(
            subject=data['subject'],
            marks=data['marks'],
        ).exclude(id__in=excluded_ids)
    )
    random.shuffle(candidates)

    for candidate in candidates:
        serialized = GeneratedQuestionSerializer(candidate).data
        transformed = transform_generated_question(
            serialized,
            department,
            data.get('language', 'english'),
        )
        question_text = normalize_question_text(transformed.get('questions'))
        if question_text in excluded_texts:
            continue

        return Response({
            'success': True,
            'message': 'Replacement question generated successfully',
            'data': {
                'question': transformed,
            },
        })

    return Response({
        'success': False,
        'message': 'No replacement question available for this subject and marks.',
    }, status=status.HTTP_404_NOT_FOUND)


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
            from ..models import Faculty
            faculty_ref = None
            if validated_data.get('faculty_id'):
                faculty_ref = Faculty.objects.filter(id=validated_data['faculty_id']).first()
            elif validated_data.get('faculty'):
                faculty_ref = Faculty.objects.filter(
                    Q(faculty_code__iexact=validated_data['faculty']) |
                    Q(faculty_name__iexact=validated_data['faculty'])
                ).first()

            exam_type = validated_data.get('exam_type', 'SCHEDULED')
            dept_name = validated_data['department']
            if exam_type == 'CENTRAL' and faculty_ref and not dept_name:
                dept_name = f"Central ({faculty_ref.faculty_code})"

            # Create exam with all fields matching the Exam model
            exam = Exam.objects.create(
                department=dept_name,
                semester=validated_data['semester'],
                total_questions=validated_data['total_questions'],
                present_question=validated_data['total_questions'],  # Set to same as total_questions
                total_marks=validated_data['total_marks'],
                duration_minutes=validated_data['duration_minutes'],
                except_semesters=validated_data.get('except_semesters', []),
                language=validated_data.get('language', 'English'),
                faculty=validated_data.get('faculty', faculty_ref.faculty_code if faculty_ref else ''),
                exam_type=exam_type,
                faculty_ref=faculty_ref
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








