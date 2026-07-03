from rest_framework import serializers


class ScrapperUploadSerializer(serializers.Serializer):
    """Serializer for uploading one-or-many .docx files via multipart form-data."""

    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        write_only=True,
        help_text="One or many .docx files",
    )

    def validate_files(self, value):
        for uploaded_file in value:
            name = getattr(uploaded_file, "name", "")
            if not name.lower().endswith(".docx"):
                raise serializers.ValidationError(f"Unsupported file type: {name}")
        return value


class AiScraperUploadSerializer(serializers.Serializer):
    """Serializer for the Gemini-based scraper: a single .pdf/.docx file plus creds."""

    file = serializers.FileField(write_only=True, help_text="A single .pdf or .docx file")
    api_key = serializers.CharField(write_only=True, trim_whitespace=True)
    model = serializers.CharField(
        required=False,
        default="gemini-3.5-flash",
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate_file(self, value):
        name = getattr(value, "name", "").lower()
        if not (name.endswith(".pdf") or name.endswith(".docx")):
            raise serializers.ValidationError(
                f"Unsupported file type: {getattr(value, 'name', '')}. Use .pdf or .docx"
            )
        return value
