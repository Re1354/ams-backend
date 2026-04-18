from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiResponse, extend_schema

from ..authentication import CustomJWTAuthentication
from ..serializers.scrapper import ScrapperUploadSerializer
from .demo_scrapper import _HAS_PYDOCX, parse_docx_fileobj


@extend_schema(
    operation_id="upload_docx_scrape_multipart",
    tags=["Document Scraper"],
    summary="Upload one or many .docx files and extract questions",
    description=(
        'Accepts multipart/form-data with key "files" as one-or-many .docx files; '
        "returns extracted JSON per file."
    ),
    request=ScrapperUploadSerializer,
    responses={200: OpenApiResponse(description="Extraction results")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def upload_docx_scrape_multipart(request):
    """Upload one-or-many .docx files in multipart form and return parsed extraction results."""
    if not _HAS_PYDOCX:
        return Response(
            {"success": False, "message": "python-docx not installed on server"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    serializer = ScrapperUploadSerializer(data=request.data)
    if serializer.is_valid():
        files = serializer.validated_data["files"]
    else:
        files = request.FILES.getlist("files")
        if not files:
            return Response(
                {
                    "success": False,
                    "message": "No files provided or invalid payload",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    results = []
    for uploaded_file in files:
        try:
            extracted = parse_docx_fileobj(uploaded_file, uploaded_file.name)
            results.append(
                {
                    "filename": uploaded_file.name,
                    "success": True,
                    "count": len(extracted),
                    "data": extracted,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "filename": getattr(uploaded_file, "name", ""),
                    "success": False,
                    "message": str(exc),
                }
            )

    return Response({"success": True, "results": results})
