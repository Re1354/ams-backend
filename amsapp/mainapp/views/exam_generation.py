from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiResponse
import random

from django.db.models import Q
from ..models import (
    ScrappedQuestion, Exam, ExamQuestion, BlocklistQuestion, Department,
    Faculty, FacultyDepartment,
)
from ..services.access_control import (
    get_user_access_scope, get_faculty_for_department, get_departments_for_faculty,
)
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


def get_faculty_department_identifiers(faculty_id):
    """
    Returns department IDs, Department instances, shortnames, and full names
    for all departments belonging to the specified faculty.
    """
    if not faculty_id:
        return {'department_ids': [], 'departments': [], 'shortnames': set(), 'names': set()}

    dept_ids = []
    for fd in FacultyDepartment.objects.filter(faculty_id=faculty_id):
        if fd.department_ids:
            dept_ids.extend(fd.department_ids)
    dept_ids = list(dict.fromkeys(dept_ids))

    depts = list(Department.objects.filter(id__in=dept_ids))
    shortnames = {d.department_shortname for d in depts if d.department_shortname}
    names = {d.department_name for d in depts if d.department_name}
    return {
        'department_ids': dept_ids,
        'departments': depts,
        'shortnames': shortnames,
        'names': names,
    }


def get_outside_department_identifiers(current_faculty_id):
    """
    Returns shortnames and names of departments that belong to OTHER faculties
    and NOT to current_faculty_id.
    """
    if not current_faculty_id:
        return {'shortnames': set(), 'names': set()}

    current_dept_ids = set()
    for fd in FacultyDepartment.objects.filter(faculty_id=current_faculty_id):
        if fd.department_ids:
            current_dept_ids.update(fd.department_ids)

    outside_dept_ids = set()
    for fd in FacultyDepartment.objects.exclude(faculty_id=current_faculty_id):
        if fd.department_ids:
            outside_dept_ids.update(fd.department_ids)

    pure_outside_ids = outside_dept_ids - current_dept_ids
    outside_depts = list(Department.objects.filter(id__in=pure_outside_ids))
    return {
        'shortnames': {d.department_shortname for d in outside_depts if d.department_shortname},
        'names': {d.department_name for d in outside_depts if d.department_name},
    }


def build_question_scope_query(exam_type, faculty_obj=None, department_obj=None):
    """
    Builds a Q object to scope question retrieval strictly to the eligible departments:
    - CENTRAL: Only departments under the selected faculty; strictly excludes outside faculties.
    - SCHEDULED: Only the selected department.
    """
    if exam_type == 'CENTRAL':
        if not faculty_obj:
            return Q(pk__in=[])

        fac_info = get_faculty_department_identifiers(faculty_obj.id)
        if not fac_info['department_ids']:
            return Q(pk__in=[])

        allowed_terms = set(fac_info['shortnames']) | set(fac_info['names'])
        allowed_expanded = set()
        for t in allowed_terms:
            if t:
                allowed_expanded.add(t)
                allowed_expanded.add(t.upper())
                allowed_expanded.add(t.lower())

        outside_info = get_outside_department_identifiers(faculty_obj.id)
        outside_terms = set(outside_info['shortnames']) | set(outside_info['names'])
        outside_expanded = set()
        for t in outside_terms:
            if t:
                outside_expanded.add(t)
                outside_expanded.add(t.upper())
                outside_expanded.add(t.lower())

        allowed_q = Q(department_shortname__in=allowed_expanded)
        if outside_expanded:
            outside_q = ~Q(department_shortname__in=outside_expanded)
            return allowed_q & outside_q
        return allowed_q

    elif exam_type == 'SCHEDULED':
        if not department_obj:
            return Q(pk__in=[])

        dept_terms = {department_obj.department_shortname, department_obj.department_name}
        dept_expanded = set()
        for t in dept_terms:
            if t:
                dept_expanded.add(t)
                dept_expanded.add(t.upper())
                dept_expanded.add(t.lower())
        return Q(department_shortname__in=dept_expanded)

    return Q()


def transform_generated_question(question_data, department, language, exam_type='SCHEDULED'):
    item = dict(question_data)
    if exam_type == 'SCHEDULED' and department:
        item['department_shortname'] = getattr(
            department,
            'department_shortname',
            item.get('department_shortname', ''),
        )
    elif not item.get('department_shortname') and department:
        item['department_shortname'] = getattr(
            department,
            'department_shortname',
            '',
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

    if exam_type == 'CENTRAL':
        faculty_id = data.get('faculty_id')
        faculty_name = data.get('faculty')
        if faculty_id:
            faculty_obj = Faculty.objects.filter(id=faculty_id).first()
        elif faculty_name:
            faculty_obj = Faculty.objects.filter(
                Q(faculty_shortname__iexact=faculty_name) | Q(faculty_name__iexact=faculty_name)
            ).first()

        if not faculty_obj:
            return Response({
                'success': False,
                'message': 'A valid faculty is required for Central exam question generation'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Authorization check
        access_scope = get_user_access_scope(request.user)
        if not access_scope['is_global']:
            user_fac_id = getattr(request.user, 'faculty_id', None)
            if not user_fac_id or user_fac_id != faculty_obj.id:
                return Response({
                    'success': False,
                    'message': 'You do not have permission to generate Central exams for this faculty.'
                }, status=status.HTTP_403_FORBIDDEN)

        fac_dept_info = get_faculty_department_identifiers(faculty_obj.id)
        if not fac_dept_info['department_ids']:
            return Response({
                'success': False,
                'message': f'No departments configured for faculty {faculty_obj.faculty_shortname}'
            }, status=status.HTTP_404_NOT_FOUND)

        department = fac_dept_info['departments'][0]
        scope_q = build_question_scope_query('CENTRAL', faculty_obj=faculty_obj)

    else:
        dept_id = data.get('department_id')
        if not dept_id:
            return Response({
                'success': False,
                'message': 'Department ID is required for scheduled exams'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            department = Department.objects.get(id=dept_id)
        except Department.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Department not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Authorization check
        access_scope = get_user_access_scope(request.user)
        if not access_scope['is_global']:
            allowed_dept_ids = access_scope.get('department_ids') or []
            if department.id not in allowed_dept_ids:
                return Response({
                    'success': False,
                    'message': 'You do not have permission to generate exams for this department.'
                }, status=status.HTTP_403_FORBIDDEN)

        faculty_obj = get_faculty_for_department(department.id)
        scope_q = build_question_scope_query('SCHEDULED', department_obj=department)
    
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
        
        # Query available questions scoped to faculty/department, excluding blocked and explicitly excluded ones
        all_excluded = list(exclude_questions) + list(blocked_question_ids)
        available_questions = ScrappedQuestion.objects.filter(
            scope_q,
            subject=subject
        ).exclude(id__in=all_excluded).distinct()
        
        if not available_questions.exists():
            scope_name = faculty_obj.faculty_shortname if exam_type == 'CENTRAL' else department.department_shortname
            return Response({
                'success': False,
                'message': f'No questions available for subject: {subject} in {scope_name}'
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
            scope_name = faculty_obj.faculty_shortname if exam_type == 'CENTRAL' else department.department_shortname
            return Response({
                'success': False,
                'message': f'Not enough questions to meet {required_marks} marks for {subject} in {scope_name}. Only {current_marks} marks available.'
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
        transform_generated_question(q, department, req_language, exam_type=exam_type)
        for q in raw_questions
    ]

    # Prepare response data
    response_data = {
        'exam_id': None,  # Not saved yet
        'department_id': department.id if (department and exam_type == 'SCHEDULED') else None,
        'faculty_id': faculty_obj.id if faculty_obj else None,
        'semester': data['semester'],
        'duration_minutes': data['duration_minutes'],
        'language': data['language'],
        'faculty': faculty_obj.faculty_shortname if faculty_obj else data.get('faculty', ''),
        'exam_type': exam_type,
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
    exam_type = data.get('exam_type', 'SCHEDULED')
    department = None
    faculty_obj = None

    if exam_type == 'CENTRAL':
        faculty_id = data.get('faculty_id')
        faculty_name = data.get('faculty')
        if faculty_id:
            faculty_obj = Faculty.objects.filter(id=faculty_id).first()
        elif faculty_name:
            faculty_obj = Faculty.objects.filter(
                Q(faculty_shortname__iexact=faculty_name) | Q(faculty_name__iexact=faculty_name)
            ).first()

        if not faculty_obj:
            return Response({
                'success': False,
                'message': 'A valid faculty is required for Central question regeneration'
            }, status=status.HTTP_400_BAD_REQUEST)

        access_scope = get_user_access_scope(request.user)
        if not access_scope['is_global']:
            user_fac_id = getattr(request.user, 'faculty_id', None)
            if not user_fac_id or user_fac_id != faculty_obj.id:
                return Response({
                    'success': False,
                    'message': 'You do not have permission to regenerate questions for this faculty.'
                }, status=status.HTTP_403_FORBIDDEN)

        fac_info = get_faculty_department_identifiers(faculty_obj.id)
        if fac_info['departments']:
            department = fac_info['departments'][0]
        scope_q = build_question_scope_query('CENTRAL', faculty_obj=faculty_obj)

    else:
        dept_id = data.get('department_id')
        if dept_id:
            try:
                department = Department.objects.get(id=dept_id)
            except Department.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Department not found',
                }, status=status.HTTP_404_NOT_FOUND)
        if not department:
            department = Department.objects.first()

        access_scope = get_user_access_scope(request.user)
        if not access_scope['is_global']:
            allowed_dept_ids = access_scope.get('department_ids') or []
            if department.id not in allowed_dept_ids:
                return Response({
                    'success': False,
                    'message': 'You do not have permission to regenerate questions for this department.'
                }, status=status.HTTP_403_FORBIDDEN)

        faculty_obj = get_faculty_for_department(department.id)
        scope_q = build_question_scope_query('SCHEDULED', department_obj=department)

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
            scope_q,
            subject=data['subject'],
            marks=data['marks'],
        ).exclude(id__in=excluded_ids).distinct()
    )
    random.shuffle(candidates)

    for candidate in candidates:
        serialized = GeneratedQuestionSerializer(candidate).data
        transformed = transform_generated_question(
            serialized,
            department,
            data.get('language', 'english'),
            exam_type=exam_type,
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
            exam_type = validated_data.get('exam_type', 'SCHEDULED')
            faculty_ref = None

            if exam_type == 'CENTRAL':
                if validated_data.get('faculty_id'):
                    faculty_ref = Faculty.objects.filter(id=validated_data['faculty_id']).first()
                elif validated_data.get('faculty'):
                    faculty_ref = Faculty.objects.filter(
                        Q(faculty_shortname__iexact=validated_data['faculty']) |
                        Q(faculty_name__iexact=validated_data['faculty'])
                    ).first()

                if not faculty_ref:
                    return Response({
                        'success': False,
                        'message': 'A valid faculty is required for Central exams.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Authorization check
                access_scope = get_user_access_scope(request.user)
                if not access_scope['is_global']:
                    user_fac_id = getattr(request.user, 'faculty_id', None)
                    if not user_fac_id or user_fac_id != faculty_ref.id:
                        return Response({
                            'success': False,
                            'message': 'You do not have permission to save Central exams for this faculty.'
                        }, status=status.HTTP_403_FORBIDDEN)

                # Faculty isolation validation on all submitted questions
                fac_info = get_faculty_department_identifiers(faculty_ref.id)
                outside_info = get_outside_department_identifiers(faculty_ref.id)
                allowed_terms = {s.upper() for s in fac_info['shortnames']} | {n.upper() for n in fac_info['names']}
                outside_terms = {s.upper() for s in outside_info['shortnames']} | {n.upper() for n in outside_info['names']}

                for q_data in validated_data['questions']:
                    q_id = q_data.get('id')
                    q_dept = (q_data.get('department_shortname') or '').strip().upper()
                    if q_id:
                        orig = ScrappedQuestion.objects.filter(id=q_id).first()
                        if orig:
                            orig_dept = (orig.department_shortname or '').strip().upper()
                            if orig_dept in outside_terms:
                                return Response({
                                    'success': False,
                                    'message': f"Question ID {q_id} belongs to outside department '{orig.department_shortname}' and cannot be saved in a Central exam for {faculty_ref.faculty_shortname}."
                                }, status=status.HTTP_400_BAD_REQUEST)
                            if allowed_terms and orig_dept not in allowed_terms:
                                return Response({
                                    'success': False,
                                    'message': f"Question ID {q_id} does not belong to any department under faculty {faculty_ref.faculty_shortname}."
                                }, status=status.HTTP_400_BAD_REQUEST)
                    if q_dept and q_dept in outside_terms:
                        return Response({
                            'success': False,
                            'message': f"Question belongs to outside department '{q_data.get('department_shortname')}' and cannot be saved in a Central exam for {faculty_ref.faculty_shortname}."
                        }, status=status.HTTP_400_BAD_REQUEST)

                dept_name = validated_data.get('department')
                if not dept_name or not str(dept_name).startswith('Central'):
                    dept_name = f"Central ({faculty_ref.faculty_shortname})"

            else:  # SCHEDULED
                dept_name = validated_data['department']
                dept_id = validated_data.get('department_id')
                department = None
                if dept_id:
                    department = Department.objects.filter(id=dept_id).first()
                if not department:
                    department = Department.objects.filter(
                        Q(department_name__iexact=dept_name) | Q(department_shortname__iexact=dept_name)
                    ).first()

                if department:
                    access_scope = get_user_access_scope(request.user)
                    if not access_scope['is_global']:
                        allowed_depts = access_scope.get('department_ids') or []
                        if department.id not in allowed_depts:
                            return Response({
                                'success': False,
                                'message': 'You do not have permission to save exams for this department.'
                            }, status=status.HTTP_403_FORBIDDEN)
                    faculty_ref = get_faculty_for_department(department.id)
                elif validated_data.get('faculty_id'):
                    faculty_ref = Faculty.objects.filter(id=validated_data['faculty_id']).first()

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
                faculty=faculty_ref.faculty_shortname if faculty_ref else (validated_data.get('faculty') or ''),
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
                dept_sn = question_data.get('department_shortname')
                if not dept_sn and question_data.get('id'):
                    orig_q = ScrappedQuestion.objects.filter(id=question_data['id']).first()
                    if orig_q and orig_q.department_shortname:
                        dept_sn = orig_q.department_shortname
                if not dept_sn:
                    dept_sn = faculty_ref.faculty_shortname if exam_type == 'CENTRAL' else (department.department_shortname if department else 'CSE')

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








