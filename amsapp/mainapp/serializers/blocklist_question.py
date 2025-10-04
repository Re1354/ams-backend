from rest_framework import serializers
from ..models import BlocklistQuestion, ScrappedQuestion, User


class BlockQuestionSerializer(serializers.Serializer):
    """Serializer for blocking a scrapped question"""
    
    question_id = serializers.IntegerField(help_text="ID of the scrapped question to block")
    remarks = serializers.CharField(max_length=1000, help_text="Reason for blocking this question")
    
    def validate_question_id(self, value):
        """Validate that the scrapped question exists"""
        if not ScrappedQuestion.objects.filter(id=value).exists():
            raise serializers.ValidationError("Scrapped question does not exist")
        return value


class BlockedQuestionSerializer(serializers.ModelSerializer):
    """Serializer for BlocklistQuestion model"""
    
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    
    class Meta:
        model = BlocklistQuestion
        fields = [
            'id', 'subject', 'questions', 'type', 'text', 'options', 'answer', 
            'marks', 'semester', 'department_shortname', 'original_question_id',
            'remarks', 'creator', 'creator_username', 
            'issue_solved', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'original_question_id', 'creator', 'creator_username', 
            'created_at', 'updated_at'
        ]


class RestoreQuestionSerializer(serializers.ModelSerializer):
    """Serializer for updating and restoring a blocked question"""
    
    class Meta:
        model = BlocklistQuestion
        fields = [
            'subject', 'questions', 'type', 'text', 'options', 'answer', 
            'marks', 'semester', 'department_shortname', 'remarks', 'issue_solved'
        ]
    
    def validate_marks(self, value):
        """Validate marks is positive"""
        if value <= 0:
            raise serializers.ValidationError("Marks must be greater than 0")
        return value
    
    def validate_type(self, value):
        """Validate question type"""
        valid_types = [choice[0] for choice in ScrappedQuestion.TYPE_CHOICES]
        if value not in valid_types:
            raise serializers.ValidationError(f"Invalid type. Must be one of: {valid_types}")
        return value