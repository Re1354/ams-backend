from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from ..models import ScrappedQuestion
from ..serializers import ScrappedQuestionSerializer, TotalQuestionsSerializer


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