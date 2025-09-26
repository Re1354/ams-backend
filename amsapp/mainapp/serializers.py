from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import ScrappedQuestion , Exam , ExamQuestion


class ScrappedQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for ScrappedQuestion model
    """
    
    @extend_schema_field({
        'type': 'object',
        'description': 'Multiple choice options for the question',
        'example': {
            "A": "Option A text",
            "B": "Option B text", 
            "C": "Option C text",
            "D": "Option D text"
        }
    })
    def get_options(self, obj):
        return obj.options
    
    @extend_schema_field({
        'type': 'array',
        'items': {'type': 'string'},
        'description': 'Correct answer(s) for the question',
        'example': ['B']
    })
    def get_answer(self, obj):
        return obj.answer
    
    class Meta:
        model = ScrappedQuestion
        fields = ['id', 'subject', 'questions', 'type', 'text', 'options', 'answer', 'marks', 'semester']
        
    def to_representation(self, instance):
        """Custom representation to ensure proper JSON formatting"""
        representation = super().to_representation(instance)
        
        # Add field descriptions
        representation_with_descriptions = {
            'id': representation['id'],  # Unique identifier for the question
            'subject': representation['subject'],  # Subject category (e.g., Mathematics, English)
            'questions': representation['questions'],  # The question text
            'type': representation['type'],  # Question type: 'option' or 'text' 
            'text': representation.get('text'),  # Additional text for text-type questions
            'options': representation.get('options'),  # Multiple choice options (for option-type questions)
            'answer': representation.get('answer'),  # Correct answer(s)
            'marks': representation['marks'],  # Points awarded for correct answer
            'semester': representation['semester']  # Academic semester/term
        }
        
        # Ensure options and answer are properly formatted
        if representation.get('options'):
            representation_with_descriptions['options'] = instance.options
        if representation.get('answer'):
            representation_with_descriptions['answer'] = instance.answer
            
        return representation_with_descriptions


class TotalQuestionsSerializer(serializers.Serializer):
    total_questions = serializers.IntegerField()
    subjects = serializers.DictField(
        child=serializers.IntegerField(),
        help_text="Dynamic mapping of subject name -> number of questions"
    )

    @extend_schema_field({
        'type': 'object',
        'description': 'Subject counts',
        'example': {
            "Mathematics": 3,
            "English": 11,
            "Physics": 5,
            "General Knowledge": 3,
            "IT - Using AI and ChatGPT": 3
        }
    })
    def get_subjects(self, obj):
        return obj.get('subjects', {})


class ExamCreateSerializer(serializers.ModelSerializer):
    subject_distribution = serializers.DictField(
        child=serializers.IntegerField(min_value=0),
        help_text="Percentage distribution of subjects (sum must be 100)"
    )
    except_semesters = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of semesters to exclude"
    )

    class Meta:
        model = Exam
        fields = ['department', 'semester', 'total_questions', 'duration_minutes', 'subject_distribution', 'except_semesters']

class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exam
        fields = "__all__"

class ExamQuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for ExamQuestion model - used for editing exam questions
    """
    
    # Make exam read-only to prevent accidental changes
    exam = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = ExamQuestion
        fields = [
            'id', 'exam', 'subject', 'question_text', 'type', 'text', 
            'options', 'answer', 'marks'
        ]
        read_only_fields = ['id', 'exam']
    
    def validate_marks(self, value):
        """Validate marks is positive"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be greater than 0")
        return value
    
    def validate_type(self, value):
        """Validate question type"""
        if value not in ['option', 'text']:
            raise serializers.ValidationError("Question type must be 'option' or 'text'")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        question_type = data.get('type', self.instance.type if self.instance else None)
        options = data.get('options', self.instance.options if self.instance else None)
        answer = data.get('answer', self.instance.answer if self.instance else None)
        
        # For option type questions, options and answer are required
        if question_type == 'option':
            if not options:
                raise serializers.ValidationError("Options are required for option-type questions")
            if not answer:
                raise serializers.ValidationError("Answer is required for option-type questions")
        
        return data
    
    def to_representation(self, instance):
        """Custom representation with proper formatting"""
        representation = super().to_representation(instance)
        
        # Ensure JSON fields are properly formatted
        if instance.options:
            representation['options'] = instance.options
        if instance.answer:
            representation['answer'] = instance.answer
            
        return representation