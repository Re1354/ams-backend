from rest_framework import serializers
from ..models import VivaRubrics, Department


class VivaRubricsSerializer(serializers.ModelSerializer):
    """Serializer for VivaRubrics model"""
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    
    class Meta:
        model = VivaRubrics
        fields = [
            'id', 'department', 'department_name', 'department_shortname', 
            'rubrics', 'marks'
        ]
        read_only_fields = ['id']

    def validate_marks(self, value):
        """Validate that marks is a positive integer"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive integer")
        return value

    def validate_department(self, value):
        """Validate that the department exists"""
        if not Department.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Department does not exist")
        return value


class VivaRubricsCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating VivaRubrics"""
    
    class Meta:
        model = VivaRubrics
        fields = ['department', 'rubrics', 'marks']

    def validate_marks(self, value):
        """Validate that marks is a positive integer"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive integer")
        return value

    def validate_rubrics(self, value):
        """Validate that rubrics is not empty"""
        if not value.strip():
            raise serializers.ValidationError("Rubrics cannot be empty")
        return value


class VivaRubricsUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating VivaRubrics"""
    
    class Meta:
        model = VivaRubrics
        fields = ['rubrics', 'marks']
        
    def validate_marks(self, value):
        """Validate that marks is a positive integer"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be a positive integer")
        return value

    def validate_rubrics(self, value):
        """Validate that rubrics is not empty"""
        if not value.strip():
            raise serializers.ValidationError("Rubrics cannot be empty")
        return value