from rest_framework import serializers
from ..models import VivaRubrics, Department, Faculty


class VivaRubricsSerializer(serializers.ModelSerializer):
    """Serializer for VivaRubrics model"""
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    faculty_name = serializers.CharField(source='faculty.faculty_name', read_only=True)
    faculty_code = serializers.CharField(source='faculty.faculty_code', read_only=True)
    
    class Meta:
        model = VivaRubrics
        fields = [
            'id', 'department', 'department_name', 'department_shortname',
            'faculty', 'faculty_name', 'faculty_code',
            'rubrics', 'marks'
        ]
        read_only_fields = ['id']

    def validate_marks(self, value):
        """Validate that marks is a positive integer"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive integer")
        return value


class VivaRubricsCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating VivaRubrics"""
    
    class Meta:
        model = VivaRubrics
        fields = ['faculty', 'department', 'rubrics', 'marks']
        extra_kwargs = {
            'faculty': {'required': False, 'allow_null': True},
            'department': {'required': False, 'allow_null': True},
        }

    def validate_marks(self, value):
        """Validate that marks is a positive integer"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive integer")
        return value

    def validate_rubrics(self, value):
        """Validate that rubrics is not empty"""
        if not value or not str(value).strip():
            raise serializers.ValidationError("Rubrics cannot be empty")
        return value

    def validate(self, attrs):
        faculty = attrs.get('faculty')
        if not faculty and not attrs.get('department'):
            raise serializers.ValidationError("Faculty must be specified.")
        return attrs


class VivaRubricsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating VivaRubrics"""
    
    class Meta:
        model = VivaRubrics
        fields = ['faculty', 'department', 'rubrics', 'marks']
        extra_kwargs = {
            'faculty': {'required': False, 'allow_null': True},
            'department': {'required': False, 'allow_null': True},
            'rubrics': {'required': False},
            'marks': {'required': False},
        }
        
    def validate_marks(self, value):
        """Validate that marks is a positive integer"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive integer")
        return value

    def validate_rubrics(self, value):
        """Validate that rubrics is not empty"""
        if value is not None and not str(value).strip():
            raise serializers.ValidationError("Rubrics cannot be empty")
        return value