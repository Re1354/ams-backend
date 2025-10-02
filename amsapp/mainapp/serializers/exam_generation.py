from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import BlocklistQuestion, ScrappedQuestion, Exam, ExamQuestion
import random


class SubjectMarksSerializer(serializers.Serializer):
    """Serializer for subject and marks in exam generation"""
    subject = serializers.CharField(max_length=255)
    marks = serializers.IntegerField(min_value=1)


class ExamGenerationRequestSerializer(serializers.Serializer):
    """Serializer for exam generation request"""
    department_id = serializers.IntegerField()
    semester = serializers.CharField(max_length=50)
    duration_minutes = serializers.IntegerField(min_value=1)
    language = serializers.CharField(max_length=50, default='english')
    faculty = serializers.CharField(max_length=255)
    subjects = SubjectMarksSerializer(many=True)
    
    # Optional fields for regeneration
    regenerate = serializers.BooleanField(default=False)
    exclude_questions = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list
    )
    
    def validate_subjects(self, value):
        """Validate that subjects list is not empty"""
        if not value:
            raise serializers.ValidationError("At least one subject is required")
        return value


class ExamQuestionSaveSerializer(serializers.Serializer):
    """Serializer for individual question data when saving exam"""
    id = serializers.IntegerField(required=False, help_text="Optional original question ID")
    subject = serializers.CharField(max_length=255)
    questions = serializers.CharField(help_text="Question text")  # Changed from question_text to questions
    type = serializers.ChoiceField(choices=[
        ('mcq', 'Multiple Choice'),
        ('option', 'Multiple Choice Option'),  # Added option type
        ('short', 'Short Answer'),
        ('long', 'Long Answer'),
        ('tf', 'True/False'),
        ('fill', 'Fill in the blank')
    ])
    text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    options = serializers.JSONField(required=False, allow_null=True)
    answer = serializers.JSONField(required=False, allow_null=True, help_text="Can be string or array")  # Changed to JSONField to handle arrays
    marks = serializers.IntegerField(min_value=1, default=1)
    semester = serializers.CharField(max_length=100, required=False, help_text="Original semester info")
    department_shortname = serializers.CharField(max_length=50, default='CSE')


class ExamSaveRequestSerializer(serializers.Serializer):
    """Serializer for saving exam with questions"""
    # Exam model fields
    department = serializers.CharField(max_length=255, help_text="Department name (not ID)")
    semester = serializers.CharField(max_length=50)
    total_questions = serializers.IntegerField(min_value=1)
    total_marks = serializers.IntegerField(min_value=1)
    duration_minutes = serializers.IntegerField(min_value=1)
    except_semesters = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
        help_text="List of semesters to exclude"
    )
    language = serializers.CharField(max_length=50, default='English')
    faculty = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    
    # Questions to be saved
    questions = ExamQuestionSaveSerializer(many=True, help_text="Array of question objects")
    
    def validate_questions(self, value):
        """Validate that questions list is not empty and matches total_questions"""
        if not value:
            raise serializers.ValidationError("At least one question is required")
        return value
    
    def validate(self, data):
        """Validate that total_questions matches the number of questions provided"""
        questions_count = len(data.get('questions', []))
        total_questions = data.get('total_questions', 0)
        
        if questions_count != total_questions:
            raise serializers.ValidationError(
                f"Number of questions ({questions_count}) must match total_questions ({total_questions})"
            )
        
        # Validate that total marks matches sum of question marks
        total_marks_from_questions = sum(q.get('marks', 1) for q in data.get('questions', []))
        declared_total_marks = data.get('total_marks', 0)
        
        if total_marks_from_questions != declared_total_marks:
            raise serializers.ValidationError(
                f"Sum of question marks ({total_marks_from_questions}) must match total_marks ({declared_total_marks})"
            )
        
        return data


class GeneratedQuestionSerializer(serializers.ModelSerializer):
    """Serializer for generated questions response"""
    
    class Meta:
        model = ScrappedQuestion
        fields = ['id', 'subject', 'questions', 'type', 'text', 'options', 'answer', 'marks', 'semester', 'department_shortname']


class GeneratedExamResponseSerializer(serializers.Serializer):
    """Serializer for exam generation response"""
    exam_id = serializers.IntegerField(required=False, allow_null=True)
    department_id = serializers.IntegerField()
    semester = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    language = serializers.CharField()
    faculty = serializers.CharField()
    total_marks = serializers.IntegerField()
    subjects = serializers.JSONField()
    questions = GeneratedQuestionSerializer(many=True)
    
    @extend_schema_field(serializers.JSONField())
    def get_subjects(self, obj):
        return obj.get('subjects', [])


class BlocklistQuestionSerializer(serializers.ModelSerializer):
    """Serializer for BlocklistQuestion model"""
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    
    class Meta:
        model = BlocklistQuestion
        fields = [
            'id', 'subject', 'questions', 'type', 'text', 'options', 'answer', 
            'marks', 'semester', 'department_shortname', 'original_question_id',
            'remarks', 'creator', 'creator_username', 'issue_solved', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'creator_username']


class BlockQuestionRequestSerializer(serializers.Serializer):
    """Serializer for blocking a question"""
    question_id = serializers.IntegerField()
    remarks = serializers.CharField()
    
    def validate_question_id(self, value):
        """Validate that the question exists"""
        try:
            ScrappedQuestion.objects.get(id=value)
        except ScrappedQuestion.DoesNotExist:
            raise serializers.ValidationError("Question does not exist")
        return value


class UnblockQuestionRequestSerializer(serializers.Serializer):
    """Serializer for unblocking a question"""
    blocklist_id = serializers.IntegerField()
    
    def validate_blocklist_id(self, value):
        """Validate that the blocklist entry exists"""
        try:
            BlocklistQuestion.objects.get(id=value)
        except BlocklistQuestion.DoesNotExist:
            raise serializers.ValidationError("Blocklist entry does not exist")
        return value