from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import AdmissionResult, Exam, Students, Department


class AdmissionResultSerializer(serializers.ModelSerializer):
    """Serializer for AdmissionResult model"""
    
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_full_name = serializers.CharField(source='student.full_name', read_only=True)
    student_f_id = serializers.CharField(source='student.f_id', read_only=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_shortname = serializers.CharField(source='department.department_shortname', read_only=True)
    exam_details = serializers.SerializerMethodField()
    
    class Meta:
        model = AdmissionResult
        fields = [
            'id', 'exam', 'student', 'student_username', 'student_full_name', 
            'student_f_id', 'department', 'department_name', 'department_shortname',
            'mcq_marks', 'viva_marks', 'total_marks', 'subject_wise_marks',
            'is_selected', 'status', 'threshold_applied', 'remarks',
            'exam_details', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'total_marks']
    
    @extend_schema_field(serializers.DictField())
    def get_exam_details(self, obj):
        """Get exam details"""
        return {
            'id': obj.exam.id,
            'department': obj.exam.department,
            'semester': obj.exam.semester,
            'total_marks': obj.exam.total_marks,
        }


class CalculateAdmissionResultsSerializer(serializers.Serializer):
    """Serializer for triggering admission results calculation"""
    
    exam_id = serializers.IntegerField(help_text="Exam ID for which to calculate admission results")
    
    def validate_exam_id(self, value):
        """Validate that exam exists"""
        if not Exam.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Exam with ID {value} does not exist")
        return value


class CalculateResultsResponseSerializer(serializers.Serializer):
    """Response serializer for calculate results operation"""
    
    success = serializers.BooleanField()
    message = serializers.CharField()
    processed_count = serializers.IntegerField()
    selected_count = serializers.IntegerField()
    not_selected_count = serializers.IntegerField()
    exam_id = serializers.IntegerField()


class AdmissionResultFilterSerializer(serializers.Serializer):
    """Serializer for filtering admission results"""
    
    exam_id = serializers.IntegerField(required=False, help_text="Filter by exam ID")
    department_id = serializers.IntegerField(required=False, help_text="Filter by department ID")
    student_id = serializers.IntegerField(required=False, help_text="Filter by student ID")
    is_selected = serializers.BooleanField(required=False, help_text="Filter by selection status")
    status = serializers.ChoiceField(
        choices=['PENDING', 'PUBLISHED', 'CANCELLED'],
        required=False,
        help_text="Filter by publication status"
    )
