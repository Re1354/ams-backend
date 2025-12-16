from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import DepartmentThreshold, Department, Exam


class DepartmentThresholdSerializer(serializers.ModelSerializer):
    """Serializer for DepartmentThreshold model"""
    
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    exam_details = serializers.SerializerMethodField()
    
    class Meta:
        model = DepartmentThreshold
        fields = [
            'id', 'exam', 'department', 'department_name', 'department_shortname',
            'min_threshold_mark', 'exam_details', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    @extend_schema_field(serializers.DictField())
    def get_exam_details(self, obj):
        """Get exam details"""
        return {
            'id': obj.exam.id,
            'department': obj.exam.department,
            'semester': obj.exam.semester,
            'total_marks': obj.exam.total_marks,
        }
    
    def validate_min_threshold_mark(self, value):
        """Validate that threshold is positive"""
        if value < 0:
            raise serializers.ValidationError("Threshold mark must be a positive number")
        return value
    
    def validate(self, data):
        """Validate that threshold doesn't exceed exam total marks"""
        exam = data.get('exam')
        threshold = data.get('min_threshold_mark')
        
        if exam and threshold and threshold > exam.total_marks:
            raise serializers.ValidationError(
                f"Threshold ({threshold}) cannot exceed exam total marks ({exam.total_marks})"
            )
        
        return data


class ThresholdMappingItemSerializer(serializers.Serializer):
    """Serializer for individual threshold mapping item"""
    
    department_id = serializers.IntegerField(help_text="Department ID")
    threshold = serializers.FloatField(
        min_value=0.0,
        help_text="Minimum marks threshold for this department"
    )
    
    def validate_department_id(self, value):
        """Validate that department exists"""
        if not Department.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Department with ID {value} does not exist")
        return value


class BulkThresholdMappingSerializer(serializers.Serializer):
    """Serializer for bulk creating/updating threshold mappings"""
    
    exam_id = serializers.IntegerField(help_text="Exam ID for which thresholds are being set")
    mappings = ThresholdMappingItemSerializer(many=True, help_text="List of department-threshold mappings")
    
    def validate_exam_id(self, value):
        """Validate that exam exists"""
        if not Exam.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Exam with ID {value} does not exist")
        return value
    
    def validate_mappings(self, value):
        """Validate that mappings list is not empty"""
        if not value:
            raise serializers.ValidationError("Mappings list cannot be empty")
        
        # Check for duplicate department IDs
        department_ids = [item['department_id'] for item in value]
        if len(department_ids) != len(set(department_ids)):
            raise serializers.ValidationError("Duplicate department IDs found in mappings")
        
        return value


class ThresholdMappingResponseSerializer(serializers.Serializer):
    """Response serializer for threshold mapping operations"""
    
    success = serializers.BooleanField()
    message = serializers.CharField()
    created_count = serializers.IntegerField()
    updated_count = serializers.IntegerField()
    data = DepartmentThresholdSerializer(many=True)
