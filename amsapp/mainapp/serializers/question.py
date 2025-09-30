from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import ScrappedQuestion


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
