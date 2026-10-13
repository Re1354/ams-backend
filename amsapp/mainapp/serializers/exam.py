from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models import Exam, ExamQuestion, ExamSchedule, ScrappedQuestion
from datetime import timedelta
from ..utils import normalize_semester_list, normalize_semester_value


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

    def validate_semester(self, value):
        try:
            return normalize_semester_value(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_except_semesters(self, value):
        try:
            return normalize_semester_list(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


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
    """Serializer for ExamSchedule model with detailed exam information"""
    exam_name = serializers.SerializerMethodField()
    exam_details = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamSchedule
        fields = ['id', 'exam', 'exam_name', 'exam_details', 'start_time', 'end_time', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_exam_name(self, obj):
        if obj.exam:
            return f"{obj.exam.department} - {obj.exam.semester}"
        return None

    @extend_schema_field(serializers.DictField())
    def get_exam_details(self, obj):
        """Get detailed exam information with department shortnames from questions"""
        if obj.exam:
            # Get unique department shortnames from exam questions
            department_shortnames = []
            seen_shortnames = set()
            for question in obj.exam.exam_questions.all():
                department_shortname = question.department_shortname
                if department_shortname and department_shortname not in seen_shortnames:
                    seen_shortnames.add(department_shortname)
                    department_shortnames.append(department_shortname)
            
            return {
                'id': obj.exam.id,
                'department': obj.exam.department,
                'semester': obj.exam.semester,
                'total_questions': obj.exam.total_questions,
                'present_question': obj.exam.present_question,
                'total_marks': obj.exam.total_marks,
                'duration_minutes': obj.exam.duration_minutes,
                'language': obj.exam.language,
                'faculty': obj.exam.faculty,
                'exam_type': getattr(obj.exam, 'exam_type', 'SCHEDULED'),
                'faculty_id': obj.exam.faculty_ref_id if getattr(obj.exam, 'faculty_ref_id', None) else None,
                'faculty_code': obj.exam.faculty_ref.faculty_code if getattr(obj.exam, 'faculty_ref', None) else None,
                'faculty_name': obj.exam.faculty_ref.faculty_name if getattr(obj.exam, 'faculty_ref', None) else None,
                'department_shortnames': department_shortnames,  # Added department shortnames from questions
                'created_at': obj.exam.created_at,
                'updated_at': obj.exam.updated_at
            }
        return None
    
    def validate(self, data):
        """Validate that end_time is after start_time"""
        if data.get('start_time') and data.get('end_time'):
            if data['end_time'] <= data['start_time']:
                raise serializers.ValidationError("End time must be after start time")
        return data


class ExamScheduleCreateSerializer(serializers.ModelSerializer):
    """Simple serializer for creating/updating ExamSchedule without exam details"""
    
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
            duration_minutes = exam.duration_minutes
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            # Add calculated end_time to validated data
            data['end_time'] = end_time
            data['exam'] = exam  # Store exam object for later use
            
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
