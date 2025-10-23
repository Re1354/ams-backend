from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..serializers.scrapper import ScrapperUploadSerializer
from ..authentication import CustomJWTAuthentication

# Use parsing helpers from demo_scrapper
from .demo_scrapper import parse_docx_fileobj, _HAS_PYDOCX


@extend_schema(
    operation_id='upload_docx_scrape_multipart',
    tags=['Document Scraper'],
    summary='Upload one or many .docx files and extract questions (multipart)',
    description='Accepts multipart/form-data with key "files" as one-or-many .docx files; returns extracted JSON per file.',
    request=ScrapperUploadSerializer,
    responses={200: OpenApiResponse(description='Extraction results')}
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def upload_docx_scrape_multipart(request):
    """Upload one-or-many .docx files in multipart form and return parsed extraction results."""
    if not _HAS_PYDOCX:
        return Response({'success': False, 'message': 'python-docx not installed on server'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    serializer = ScrapperUploadSerializer(data=request.data)
    # For multipart, DRF will parse request.FILES; allow serializer validation but also accept direct files
    if not serializer.is_valid():
        # Try fallback: when files provided as request.FILES.getlist('files')
        files = request.FILES.getlist('files')
        if not files:
            return Response({'success': False, 'message': 'No files provided or invalid payload', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    else:
        files = serializer.validated_data.get('files')

    results = []
    for f in files:
        try:
            if not f.name.lower().endswith('.docx'):
                results.append({'filename': f.name, 'success': False, 'message': 'Unsupported file type'})
                continue
            extracted = parse_docx_fileobj(f, f.name)
            results.append({'filename': f.name, 'success': True, 'count': len(extracted), 'data': extracted})
        except Exception as e:
            results.append({'filename': getattr(f, 'name', ''), 'success': False, 'message': str(e)})

    return Response({'success': True, 'results': results})
