from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import ScrappedQuestion, Exam, ExamQuestion, ExamSchedule, Students, Submission


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


class ExamScheduleSerializer(serializers.ModelSerializer):
    """Serializer for ExamSchedule model"""
    
    class Meta:
        model = ExamSchedule
        fields = ['id', 'exam', 'start_time', 'end_time', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def validate(self, data):
        """Validate that end_time is after start_time"""
        if data.get('start_time') and data.get('end_time'):
            if data['end_time'] <= data['start_time']:
                raise serializers.ValidationError("End time must be after start time")
        return data


class StudentsSerializer(serializers.ModelSerializer):
    """Serializer for Students model"""
    
    class Meta:
        model = Students
        fields = ['id', 'username', 'password', 'f_id', 'full_name', 'email', 'created_at']
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


class ExamResultSerializer(serializers.Serializer):
    """Serializer for exam results"""
    
    exam_id = serializers.IntegerField()
    student_id = serializers.IntegerField()
    student_username = serializers.CharField()
    total_questions = serializers.IntegerField()
    answered_questions = serializers.IntegerField()
    correct_answers = serializers.IntegerField()
    total_marks = serializers.IntegerField()
    obtained_marks = serializers.IntegerField()
    percentage = serializers.FloatField()
    subject_wise_results = serializers.DictField()
    
    class Meta:
        fields = [
            'exam_id', 'student_id', 'student_username', 'total_questions', 
            'answered_questions', 'correct_answers', 'total_marks', 'obtained_marks', 
            'percentage', 'subject_wise_results'
        ]


class CreateExamScheduleSerializer(serializers.Serializer):
    """
    Serializer for creating exam schedules
    Auto-calculates end_time based on exam duration
    """
    exam_id = serializers.IntegerField(
        help_text="ID of the exam to schedule (must exist in Exam table)",
        min_value=1
    )
    start_time = serializers.DateTimeField(
        help_text="Start time of the exam in ISO 8601 format (e.g., 2024-12-15T10:00:00Z)"
    )
    is_active = serializers.BooleanField(
        default=True,
        required=False,
        help_text="Whether the schedule is active (default: true)"
    )
    
    def validate_exam_id(self, value):
        """
        Validate that exam exists
        """
        from .models import Exam
        try:
            exam = Exam.objects.get(id=value)
            # Store exam instance for later use in validate method
            self._exam = exam
            return value
        except Exam.DoesNotExist:
            raise serializers.ValidationError(f"Exam with ID {value} does not exist")
    
    def validate(self, data):
        """
        Auto-calculate end_time based on exam duration
        """
        if hasattr(self, '_exam'):
            exam = self._exam
            start_time = data['start_time']
            
            # Calculate end_time by adding exam duration to start_time
            from datetime import timedelta
            duration_minutes = exam.duration_minutes
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            # Add calculated end_time to validated data
            data['end_time'] = end_time
            data['exam'] = exam  # Store exam object for later use
            
        return data