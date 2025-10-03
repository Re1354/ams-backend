from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import PublishedExam, Exam


class PublishedExamSerializer(serializers.ModelSerializer):
    """Serializer for PublishedExam model"""
    
    exam_details = serializers.SerializerMethodField()
    
    class Meta:
        model = PublishedExam
        fields = ['id', 'exam', 'is_published', 'published_at', 'created_at', 'updated_at', 'exam_details']
        read_only_fields = ['id', 'published_at', 'created_at', 'updated_at', 'exam_details']
    
    @extend_schema_field(serializers.DictField())
    def get_exam_details(self, obj):
        """Get exam details"""
        return {
            'id': obj.exam.id,
            'department': obj.exam.department,
            'semester': obj.exam.semester,
            'total_questions': obj.exam.total_questions,
        }


class TogglePublishSerializer(serializers.Serializer):
    """Serializer for toggling exam publication status"""
    
    exam_id = serializers.IntegerField(help_text="ID of the exam to toggle publication status")
    
    def validate_exam_id(self, value):
        """Validate that exam exists"""
        if not Exam.objects.filter(id=value).exists():
            raise serializers.ValidationError("Exam does not exist")
        return value


class SubjectResultSerializer(serializers.Serializer):
    """Serializer for individual subject results"""
    
    subject_id = serializers.IntegerField()
    subject_name = serializers.CharField()
    total_questions = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    wrong_answers = serializers.IntegerField()
    score_percentage = serializers.FloatField()


class EnhancedExamResultSerializer(serializers.Serializer):
    """Enhanced serializer for exam results with subject breakdown"""
    
    student_id = serializers.IntegerField()
    exam_id = serializers.IntegerField()
    student_name = serializers.CharField()
    exam_details = serializers.DictField()
    results = serializers.DictField()
    subjects = serializers.ListField(child=SubjectResultSerializer())


class ResultsSummarySerializer(serializers.Serializer):
    """Serializer for results summary with pagination"""
    
    pagination = serializers.DictField()
    results = serializers.ListField(child=EnhancedExamResultSerializer())
    filters = serializers.DictField()