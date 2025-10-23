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
