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
