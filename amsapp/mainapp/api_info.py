from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema


@extend_schema(
    summary="API Information",
    description="Get basic information about the AMS DIU Backend API",
    tags=['Information']
)
@api_view(['GET'])
def api_info(request):
    """
    API Information endpoint
    """
    return Response({
        'name': 'AMS DIU Backend API',
        'version': '1.0.0',
        'description': 'Academic Management System API for DIU with scrapped questions and educational content',
        'documentation': {
            'swagger': request.build_absolute_uri('/api/docs/'),
            'redoc': request.build_absolute_uri('/api/redoc/'),
            'schema': request.build_absolute_uri('/api/schema/')
        },
        'endpoints': {
            'all_questions': request.build_absolute_uri('/api/all-scrapped-questions/'),
            'questions_stats': request.build_absolute_uri('/api/questions-stats/'),
        },
        'features': [
            'Scrapped Questions Management',
            'Advanced Filtering and Search',
            'Statistics and Analytics',
            'REST API with Swagger Documentation',
            'CORS Support for Frontend Integration'
        ]
    })


def home(request):
    """
    Home page with API documentation links
    """
    context = {
        'api_title': 'AMS DIU Backend API',
        'api_description': 'Academic Management System API for DIU',
        'swagger_url': '/api/docs/',
        'redoc_url': '/api/redoc/',
        'api_info_url': '/api/info/'
    }
    return render(request, 'home.html', context)