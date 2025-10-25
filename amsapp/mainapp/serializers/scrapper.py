from rest_framework import serializers


class ScrapperUploadSerializer(serializers.Serializer):
    """Serializer for multipart docx upload in Swagger/OpenAPI.

    Use 'files' as the multipart field (one-or-many files allowed).
    """
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        write_only=True,
        help_text='One or many .docx files'
    )

    def validate_files(self, value):
        # Ensure each file has .docx extension
        for f in value:
            name = getattr(f, 'name', '')
            if not name.lower().endswith('.docx'):
                raise serializers.ValidationError(f'Unsupported file type: {name}')
        return value
from rest_framework import serializers

class ScrapperUploadSerializer(serializers.Serializer):
    """Serializer for uploading one-or-many .docx files via multipart form-data.

    Use field name 'files' as a list of uploaded files.
    """
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        write_only=True
    )
