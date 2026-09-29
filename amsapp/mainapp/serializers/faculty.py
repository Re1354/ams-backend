from rest_framework import serializers
from ..models.faculty import Faculty


class FacultySerializer(serializers.ModelSerializer):
    """Serializer for Faculty model"""

    class Meta:
        model = Faculty
        fields = ['id', 'faculty_name', 'faculty_shortname']

    def validate_faculty_name(self, value):
        """Validate faculty name is unique"""
        if self.instance:
            if Faculty.objects.filter(faculty_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Faculty name already exists")
        else:
            if Faculty.objects.filter(faculty_name=value).exists():
                raise serializers.ValidationError("Faculty name already exists")
        return value


class FacultyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating Faculty model"""

    class Meta:
        model = Faculty
        fields = ['faculty_name', 'faculty_shortname']

    def validate_faculty_name(self, value):
        """Validate faculty name is unique and not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Faculty name cannot be empty")

        value = value.strip()

        if self.instance:
            if Faculty.objects.filter(faculty_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Faculty name already exists")
        else:
            if Faculty.objects.filter(faculty_name=value).exists():
                raise serializers.ValidationError("Faculty name already exists")
        return value

    def validate_faculty_shortname(self, value):
        """Validate faculty shortname is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Faculty shortname cannot be empty")
        return value.strip().upper()
