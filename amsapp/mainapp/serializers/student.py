from rest_framework import serializers
from ..models import Students, Submission, ExamQuestion, Exam


class StudentsSerializer(serializers.ModelSerializer):
    """Serializer for Students model"""
    
    class Meta:
        model = Students
        fields = ['id', 'username', 'password', 'f_id', 'full_name', 'email', 'department_shortname', 'created_at', 'ssc', 'hsc', 'diploma']
        read_only_fields = ['id', 'created_at']
        extra_kwargs = {
            'password': {'write_only': True}  # Never return password in API responses
        }
    
    def validate_username(self, value):
        """Validate username is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Students.objects.filter(username=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Username already exists")
        else:
            # For creation
            if Students.objects.filter(username=value).exists():
                raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_ssc(self, value):
        """Validate SSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("SSC marks cannot be negative")
        return value
    
    def validate_hsc(self, value):
        """Validate HSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("HSC marks cannot be negative")
        return value
    
    def validate_diploma(self, value):
        """Validate Diploma marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Diploma marks cannot be negative")
        return value


class StudentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating students"""
    
    class Meta:
        model = Students
        fields = ['username', 'password', 'f_id', 'full_name', 'email', 'department_shortname', 'ssc', 'hsc', 'diploma']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def validate_username(self, value):
        """Validate username is unique"""
        if Students.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_ssc(self, value):
        """Validate SSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("SSC marks cannot be negative")
        return value
    
    def validate_hsc(self, value):
        """Validate HSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("HSC marks cannot be negative")
        return value
    
    def validate_diploma(self, value):
        """Validate Diploma marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Diploma marks cannot be negative")
        return value


class StudentUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating students"""
    
    class Meta:
        model = Students
        fields = ['username', 'f_id', 'full_name', 'email', 'department_shortname', 'ssc', 'hsc', 'diploma']
        # Note: Password update should be handled separately for security
    
    def validate_username(self, value):
        """Validate username is unique"""
        if self.instance and Students.objects.filter(username=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_ssc(self, value):
        """Validate SSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("SSC marks cannot be negative")
        return value
    
    def validate_hsc(self, value):
        """Validate HSC marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("HSC marks cannot be negative")
        return value
    
    def validate_diploma(self, value):
        """Validate Diploma marks is non-negative"""
        if value < 0:
            raise serializers.ValidationError("Diploma marks cannot be negative")
        return value


class SubmissionSerializer(serializers.ModelSerializer):
    """Serializer for Submission model"""
    
    student_username = serializers.CharField(source='student.username', read_only=True)
    exam_title = serializers.CharField(source='exam.department', read_only=True)
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_marks = serializers.IntegerField(source='question.marks', read_only=True)
    
    class Meta:
        model = Submission
        fields = [
            'id', 'student', 'exam', 'question', 'answer', 'is_correct', 
            'submitted_at', 'student_username', 'exam_title', 'question_text', 'question_marks'
        ]
        read_only_fields = ['id', 'submitted_at', 'student_username', 'exam_title', 'question_text', 'question_marks']
    
    def validate(self, data):
        """Validate that student hasn't already submitted this question"""
        student = data.get('student')
        exam = data.get('exam')
        question = data.get('question')
        
        if self.instance is None:  # Only for creation, not updates
            if Submission.objects.filter(student=student, exam=exam, question=question).exists():
                raise serializers.ValidationError("Student has already submitted answer for this question")
        
        return data
