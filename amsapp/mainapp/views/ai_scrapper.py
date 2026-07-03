from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiResponse, extend_schema

from ..authentication import CustomJWTAuthentication
from ..serializers.scrapper import AiScraperUploadSerializer
from ..services.gemini_scraper import GeminiScrapeError, scrape_with_gemini


@extend_schema(
    operation_id="ai_scrape_upload",
    tags=["Document Scraper"],
    summary="Extract questions from a PDF/DOCX using Gemini AI",
    description=(
        "Accepts multipart/form-data with a single `file` (.pdf or .docx), a "
        "`api_key` (Gemini), and an optional `model`. Uses Google Gemini to "
        "extract questions and returns them in the same envelope as /api/scrape-docx/ "
        "so the result can be posted to /api/scrapped-questions/insert/."
    ),
    request=AiScraperUploadSerializer,
    responses={200: OpenApiResponse(description="Extraction results")},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def ai_scrape_upload(request):
    """Upload a single .pdf/.docx and return AI-extracted questions."""
    serializer = AiScraperUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"success": False, "message": "Invalid payload", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    uploaded_file = serializer.validated_data["file"]
    api_key = serializer.validated_data["api_key"]
    model = serializer.validated_data.get("model") or "gemini-3.5-flash"

    try:
        file_bytes = uploaded_file.read()
        data = scrape_with_gemini(
            file_bytes=file_bytes,
            filename=uploaded_file.name,
            mimetype=getattr(uploaded_file, "content_type", "") or "",
            api_key=api_key,
            model=model,
        )
        result = {
            "filename": uploaded_file.name,
            "success": True,
            "count": len(data),
            "data": data,
        }
    except GeminiScrapeError as exc:
        return Response(
            {
                "success": False,
                "results": [
                    {"filename": uploaded_file.name, "success": False, "message": str(exc)}
                ],
                "message": str(exc),
            },
            # 400 (not 502) so a Gemini/config error is distinguishable from a
            # real gateway/timeout 502 coming from nginx-proxy/gunicorn.
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return Response(
            {"success": False, "message": f"Unexpected error: {exc}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({"success": True, "results": [result]})
