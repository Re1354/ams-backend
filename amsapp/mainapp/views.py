from django.shortcuts import render
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import Q
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from drf_spectacular.types import OpenApiTypes
from .models import ScrappedQuestion
from .serializers import ScrappedQuestionSerializer

# Create your views here.

@extend_schema(
    summary="Get all scrapped questions",
    description="Retrieve all scrapped questions with optional filtering by subject, type, semester, and search functionality.",
    parameters=[
        OpenApiParameter(
            name='subject',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter questions by subject (case-insensitive partial match)',
            examples=[
                OpenApiExample('Mathematics', value='Mathematics'),
                OpenApiExample('English', value='English'),
                OpenApiExample('Physics', value='Physics')
            ]
        ),
        OpenApiParameter(
            name='type',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter questions by type',
            enum=['option', 'text']
        ),
        OpenApiParameter(
            name='semester',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Filter questions by semester (case-insensitive partial match)',
            examples=[
                OpenApiExample('General', value='General'),
                OpenApiExample('Fall 2024', value='Fall 2024')
            ]
        ),
        OpenApiParameter(
            name='search',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Search in question text and subject',
            examples=[
                OpenApiExample('Search for AI', value='artificial intelligence'),
                OpenApiExample('Search for math', value='matrix')
            ]
        ),
        OpenApiParameter(
            name='page',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Page number for pagination'
        ),
    ],
    tags=['Questions'],
    responses={200: ScrappedQuestionSerializer(many=True)}
)
class AllScrappedQuestionsView(generics.ListAPIView):
    """
    API endpoint to get all scrapped questions
    Supports filtering by subject, type, and semester
    """
    queryset = ScrappedQuestion.objects.all()
    serializer_class = ScrappedQuestionSerializer
    
    def get_queryset(self):
        queryset = ScrappedQuestion.objects.all()
        
        # Filter by subject
        subject = self.request.query_params.get('subject', None)
        if subject is not None:
            queryset = queryset.filter(subject__icontains=subject)
        
        # Filter by type
        question_type = self.request.query_params.get('type', None)
        if question_type is not None:
            queryset = queryset.filter(type=question_type)
        
        # Filter by semester
        semester = self.request.query_params.get('semester', None)
        if semester is not None:
            queryset = queryset.filter(semester__icontains=semester)
        
        # Search in questions text
        search = self.request.query_params.get('search', None)
        if search is not None:
            queryset = queryset.filter(
                Q(questions__icontains=search) | 
                Q(subject__icontains=search)
            )
        
        return queryset.order_by('id')


@extend_schema(
    summary="Get questions statistics",
    description="Get comprehensive statistics about all questions including counts by subject, type, and semester.",
    tags=['Statistics'],
    responses={
        200: {
            'type': 'object',
            'properties': {
                'total_questions': {'type': 'integer', 'description': 'Total number of questions'},
                'by_subject': {
                    'type': 'object',
                    'description': 'Question count grouped by subject',
                    'example': {
                        'Mathematics': 3,
                        'English': 11,
                        'Physics': 5
                    }
                },
                'by_type': {
                    'type': 'object',
                    'description': 'Question count grouped by type',
                    'example': {
                        'option': 25,
                        'text': 0
                    }
                },
                'by_semester': {
                    'type': 'object',
                    'description': 'Question count grouped by semester',
                    'example': {
                        'General': 25
                    }
                },
                'subjects': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of all available subjects'
                },
                'semesters': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of all available semesters'
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
        'by_subject': subject_counts,
        'by_type': type_counts,
        'by_semester': semester_counts,
        'subjects': list(subjects),
        'semesters': list(semesters)
    })
