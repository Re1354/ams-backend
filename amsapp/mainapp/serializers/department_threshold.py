from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import DepartmentThreshold, Department, Exam


class DepartmentThresholdSerializer(serializers.ModelSerializer):
    """Serializer for DepartmentThreshold model (semester-based approach)"""
    
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    
    class Meta:
        model = DepartmentThreshold
        fields = [
            'id', 'department', 'department_name', 'department_shortname',
            'semester', 'min_threshold_mark', 'seat_limit', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_min_threshold_mark(self, value):
        """Validate that threshold is positive"""
        if value < 0:
            raise serializers.ValidationError("Threshold mark must be a positive number")
        return value
    
    def validate_seat_limit(self, value):
        """Validate that seat limit is at least 1"""
        if value < 1:
            raise serializers.ValidationError("Seat limit must be at least 1")
        return value


class ThresholdMappingItemSerializer(serializers.Serializer):
    """Serializer for individual threshold mapping item (semester-based)"""
    
    department_id = serializers.IntegerField(help_text="Department ID")
    threshold = serializers.FloatField(
        min_value=0.0,
        help_text="Minimum marks threshold for this department"
    )
    seat_limit = serializers.IntegerField(
        min_value=1,
        help_text="Maximum number of students to accept in this semester"
    )
    
    def validate_department_id(self, value):
        """Validate that department exists"""
        if not Department.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Department with ID {value} does not exist")
        return value


class BulkThresholdMappingSerializer(serializers.Serializer):
    """Serializer for bulk creating/updating threshold mappings by semester"""
    
    semester = serializers.CharField(
        max_length=20,
        help_text="Semester in format 'Spring 2025', 'Summer 2025', 'Fall 2025', etc."
    )
    mappings = ThresholdMappingItemSerializer(
        many=True,
        help_text="List of department-threshold mappings for this semester"
    )
    
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
