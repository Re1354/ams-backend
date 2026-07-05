from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from ..models import ScrappedQuestion
from ..serializers import (
    BulkDeleteScrappedQuestionsSerializer,
    ScrappedQuestionSerializer,
    TotalQuestionsSerializer,
)
from django.db import transaction
from rest_framework.decorators import permission_classes, authentication_classes, api_view
from rest_framework.permissions import IsAuthenticated
from ..authentication import CustomJWTAuthentication
from drf_spectacular.utils import OpenApiResponse
from django.shortcuts import get_object_or_404
from ..utils import normalize_semester_filter
from ..utils.question_ingestion import (
    ingest_scraped_question_entries,
    validate_scraped_question_item,
)


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
            queryset = queryset.filter(semester__icontains=normalize_semester_filter(semester))
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
    summary="Delete a question-bank item",
    description="Permanently deletes one question from the scrapped question bank.",
    tags=['Questions'],
    responses={200: OpenApiResponse(description='Question deleted successfully')}
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def delete_scrapped_question(request, question_id):
    question = get_object_or_404(ScrappedQuestion, id=question_id)
    subject = question.subject
    question.delete()

    return Response({
        'success': True,
        'message': 'Question deleted successfully.',
        'deleted_id': question_id,
        'subject': subject,
    })


@extend_schema(
    summary="Bulk delete question-bank items",
    description="Permanently deletes multiple questions from the scrapped question bank.",
    tags=['Questions'],
    request=BulkDeleteScrappedQuestionsSerializer,
    responses={200: OpenApiResponse(description='Questions deleted successfully')}
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def bulk_delete_scrapped_questions(request):
    serializer = BulkDeleteScrappedQuestionsSerializer(data=request.data)
    if not serializer.is_valid():
        return Response({
            'success': False,
            'message': 'Invalid request data',
            'errors': serializer.errors,
        }, status=status.HTTP_400_BAD_REQUEST)

    question_ids = serializer.validated_data['question_ids']
    queryset = ScrappedQuestion.objects.filter(id__in=question_ids)
    found_ids = list(queryset.values_list('id', flat=True))
    missing_ids = sorted(set(question_ids) - set(found_ids))

    if not found_ids:
        return Response({
            'success': False,
            'message': 'No matching question-bank items were found.',
            'missing_ids': missing_ids,
        }, status=status.HTTP_404_NOT_FOUND)

    with transaction.atomic():
        deleted_count, _ = queryset.delete()

    message = f"Deleted {len(found_ids)} question-bank item(s) successfully."
    if missing_ids:
        message += ' Some requested IDs were not found.'

    return Response({
        'success': True,
        'message': message,
        'deleted_count': len(found_ids),
        'requested_count': len(question_ids),
        'missing_ids': missing_ids,
        'deleted_ids': sorted(found_ids),
        'raw_deleted_count': deleted_count,
    }, status=status.HTTP_200_OK)


@extend_schema(
    operation_id='update_scrapped_question',
    tags=['Questions'],
    summary='Update a question-bank item',
    description=(
        'Accepts the scraper item shape (subject, question_bangla, question_english, '
        'options, answer, semester, department) and updates the ScrappedQuestion. '
        'Validated with the same rules as inserts.'
    ),
    request=None,
    responses={200: OpenApiResponse(description='Question updated successfully')},
)
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def update_scrapped_question(request, question_id):
    question = ScrappedQuestion.objects.filter(id=question_id).first()
    if not question:
        return Response(
            {'success': False, 'message': 'Question not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    payload = dict(request.data)
    # Preserve stored marks unless the caller sends them explicitly.
    payload.setdefault('marks', question.marks)

    normalized, issues = validate_scraped_question_item(payload)
    if issues:
        return Response(
            {'success': False, 'message': 'Question is invalid.', 'issues': issues},
            status=status.HTTP_400_BAD_REQUEST,
        )

    question.subject = normalized['subject']
    question.questions = {
        'bangla': normalized['question_bangla'],
        'english': normalized['question_english'],
        'both': normalized['question_both'],
    }
    question.type = normalized['type']
    question.options = normalized['options']
    question.answer = normalized['answer']
    question.marks = normalized['marks']
    question.semester = normalized['semester']
    question.department_shortname = normalized['department_shortname'] or 'CSE'
    question.save()

    return Response({
        'success': True,
        'message': 'Question updated successfully.',
        'data': ScrappedQuestionSerializer(question).data,
    })


@extend_schema(
    operation_id='insert_scrapped_questions',
    tags=['Questions'],
    summary='Insert scrapped questions in bulk',
    description='Accepts scraper results (list of files with data) and inserts each question into scrapped_questions table.',
    request=None,
    responses={201: OpenApiResponse(description='Questions inserted successfully')}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def insert_scrapped_questions(request):
    """Insert scrapped questions from scraper output into ScrappedQuestion model."""
    payload = request.data

    # Accept either {'results': [...]} or directly a list
    entries = []
    if isinstance(payload, dict) and 'results' in payload:
        entries = payload.get('results') or []
    elif isinstance(payload, list):
        entries = payload
    else:
        return Response({'success': False, 'message': 'Invalid payload. Expected {"results": [...] } or an array.'}, status=400)

    try:
        summary = ingest_scraped_question_entries(entries)
        return Response({'success': True, **summary}, status=201)

    except Exception as e:
        return Response({'success': False, 'message': str(e)}, status=500)
