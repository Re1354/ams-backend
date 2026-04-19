from rest_framework import serializers
from ..models.exam import Exam
from ..models.viva_marks import VivaMarks
from ..models.students import Students


class VivaMarksSerializer(serializers.ModelSerializer):
    """Serializer for VivaMarks model"""
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_full_name = serializers.CharField(source='student.full_name', read_only=True)
    
    class Meta:
        model = VivaMarks
        fields = [
            'id', 'student', 'student_username', 'student_full_name', 
            'marks', 'rubrics_marks', 'remarks'
        ]
        read_only_fields = ['id']

    def validate_marks(self, value):
        """Validate that marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Marks cannot be negative")
        return value

    def validate_student(self, value):
        """Validate that the student exists"""
        if not Students.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("Student does not exist")
        return value


class VivaMarksCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating VivaMarks"""
    exam_id = serializers.IntegerField(required=False, write_only=True)
    
    class Meta:
        model = VivaMarks
        fields = ['exam_id', 'marks', 'rubrics_marks', 'remarks']

    def validate_exam_id(self, value):
        """Validate that the exam exists when provided"""
        if not Exam.objects.filter(id=value).exists():
            raise serializers.ValidationError("Exam does not exist")
        return value

    def validate_marks(self, value):
        """Validate that marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Marks cannot be negative")
        return value

    def validate_rubrics_marks(self, value):
        """Validate that rubrics_marks is a proper JSON object"""
        if not isinstance(value, dict):
            raise serializers.ValidationError("Rubrics marks must be a JSON object")
        return value
