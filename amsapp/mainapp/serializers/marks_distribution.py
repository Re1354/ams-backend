from rest_framework import serializers
from ..models import MarksDistribution, Department


class MarksDistributionSerializer(serializers.ModelSerializer):
    """Serializer for MarksDistribution model"""
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    
    class Meta:
        model = MarksDistribution
        fields = [
            'id', 'department', 'department_name', 'department_shortname', 
            'ssc', 'hsc', 'diploma', 'main_marks'
        ]
        read_only_fields = ['id']

    def validate_ssc(self, value):
        """Validate that SSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("SSC marks cannot be negative")
        return value

    def validate_hsc(self, value):
        """Validate that HSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("HSC marks cannot be negative")
        return value

    def validate_diploma(self, value):
        """Validate that Diploma marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Diploma marks cannot be negative")
        return value
    def validate_main_marks(self, value):
        """Validate that Main Marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Main Marks cannot be negative")
        return value
    
    def validate_department(self, value):
        """Validate that the department exists"""
        if not Department.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Department does not exist")
        return value


class MarksDistributionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating MarksDistribution"""
    
    class Meta:
        model = MarksDistribution
        fields = ['department', 'ssc', 'hsc', 'diploma', 'main_marks']

    def validate_ssc(self, value):
        """Validate that SSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("SSC marks cannot be negative")
        return value

    def validate_hsc(self, value):
        """Validate that HSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("HSC marks cannot be negative")
        return value

    def validate_diploma(self, value):
        """Validate that Diploma marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Diploma marks cannot be negative")
        return value

    def validate_main_marks(self, value):
        """Validate that Main Marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Main Marks cannot be negative")
        return value    

    def validate(self, data):
        """Validate that at least one mark is greater than 0"""
        if data.get('ssc', 0) == 0 and data.get('hsc', 0) == 0 and data.get('diploma', 0) == 0 and data.get('main_marks', 0) == 0:
            raise serializers.ValidationError("At least one mark (SSC, HSC, Diploma, or Main Marks) must be greater than 0")
        return data


class MarksDistributionUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating MarksDistribution"""
    
    class Meta:
        model = MarksDistribution
        fields = ['ssc', 'hsc', 'diploma', 'main_marks']
        
    def validate_ssc(self, value):
        """Validate that SSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("SSC marks cannot be negative")
        return value

    def validate_hsc(self, value):
        """Validate that HSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("HSC marks cannot be negative")
        return value

    def validate_diploma(self, value):
        """Validate that Diploma marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Diploma marks cannot be negative")
        return value

    def validate_main_marks(self, value):   
        """Validate that Main Marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Main Marks cannot be negative")
        return value    

    def validate(self, data):
        """Validate that at least one mark is greater than 0"""
        if all(data.get(field, 1) == 0 for field in ['ssc', 'hsc', 'diploma', 'main_marks']):
            raise serializers.ValidationError("At least one mark (SSC, HSC, Diploma, or Main Marks) must be greater than 0")
        return data