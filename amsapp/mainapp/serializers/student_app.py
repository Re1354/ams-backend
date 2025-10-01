from rest_framework import serializers


class StudentLoginSerializer(serializers.Serializer):
    """Serializer for student login"""
    username = serializers.CharField(required=True, help_text="Student username")
    password = serializers.CharField(required=True, help_text="Student password")


class SubmissionItemSerializer(serializers.Serializer):
    """Serializer for individual submission item"""
    question_id = serializers.IntegerField(required=True, help_text="ID of the exam question")
    answer = serializers.CharField(required=True, help_text="Student's answer to the question")


class ExamSubmissionSerializer(serializers.Serializer):
    """Serializer for exam submission"""
    student_id = serializers.IntegerField(required=True, help_text="ID of the student submitting the exam")
    submissions = SubmissionItemSerializer(many=True, required=True, help_text="List of question answers")
    
    def validate_submissions(self, value):
        """Validate that submissions is not empty"""
        if not value:
            raise serializers.ValidationError("At least one answer submission is required")
        return value


class StudentLoginResponseSerializer(serializers.Serializer):
    """Serializer for student login response"""
    message = serializers.CharField()
    student = serializers.DictField()


class ExamSubmissionResponseSerializer(serializers.Serializer):
    """Serializer for exam submission response"""
    message = serializers.CharField()
    total_submitted = serializers.IntegerField()