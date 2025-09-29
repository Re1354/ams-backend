from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.contrib.auth.hashers import check_password, make_password
from .models import ScrappedQuestion, Exam, ExamQuestion, ExamSchedule, Students, Submission, User, Role, Menu, RoleMenu


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


# Authentication and User Management Serializers

class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model"""
    
    class Meta:
        model = Role
        fields = ['id', 'role_name']
        
    def validate_role_name(self, value):
        """Validate role name is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Role.objects.filter(role_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Role name already exists")
        else:
            # For creation
            if Role.objects.filter(role_name=value).exists():
                raise serializers.ValidationError("Role name already exists")
        return value


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model with role details"""
    
    role_name = serializers.CharField(source='role.role_name', read_only=True)
    role_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'role_id', 'role_name', 'created_at']
        read_only_fields = ['id', 'created_at', 'role_name']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def validate_username(self, value):
        """Validate username is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if User.objects.filter(username=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Username already exists")
        else:
            # For creation
            if User.objects.filter(username=value).exists():
                raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_email(self, value):
        """Validate email is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if User.objects.filter(email=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Email already exists")
        else:
            # For creation
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email already exists")
        return value
    
    def validate_role_id(self, value):
        """Validate role exists"""
        if value is not None:
            try:
                Role.objects.get(id=value)
            except Role.DoesNotExist:
                raise serializers.ValidationError("Role does not exist")
        return value
    
    def create(self, validated_data):
        """Create user with hashed password"""
        role_id = validated_data.pop('role_id', None)
        password = validated_data.pop('password')
        
        # Hash password
        validated_data['password'] = make_password(password)
        
        # Create user
        user = User.objects.create(**validated_data)
        
        # Set role if provided
        if role_id:
            role = Role.objects.get(id=role_id)
            user.role = role
            user.save()
        
        return user
    
    def update(self, instance, validated_data):
        """Update user with hashed password if provided"""
        role_id = validated_data.pop('role_id', None)
        password = validated_data.pop('password', None)
        
        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update password if provided
        if password:
            instance.password = make_password(password)
        
        # Update role if provided
        if role_id is not None:
            if role_id == 0:  # Allow setting role to null
                instance.role = None
            else:
                role = Role.objects.get(id=role_id)
                instance.role = role
        
        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    
    username = serializers.CharField(max_length=100)
    password = serializers.CharField(max_length=255, write_only=True)
    
    def validate(self, data):
        """Validate user credentials"""
        username = data.get('username')
        password = data.get('password')
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials")
        
        if not check_password(password, user.password):
            raise serializers.ValidationError("Invalid credentials")
        
        data['user'] = user
        return data


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for user with role information"""
    
    role_details = RoleSerializer(source='role', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'created_at', 'role_details']
        read_only_fields = ['id', 'username', 'email', 'created_at']


class MenuSerializer(serializers.ModelSerializer):
    """Serializer for Menu model"""
    
    class Meta:
        model = Menu
        fields = ['id', 'label', 'icon', 'link']
        
    def validate_label(self, value):
        """Validate menu label is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Menu.objects.filter(label=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Menu label already exists")
        else:
            # For creation
            if Menu.objects.filter(label=value).exists():
                raise serializers.ValidationError("Menu label already exists")
        return value
    
    def validate_link(self, value):
        """Validate menu link format and uniqueness"""
        # Ensure link starts with /
        if not value.startswith('/'):
            value = '/' + value
            
        # Check uniqueness
        if self.instance:
            # For updates, exclude the current instance
            if Menu.objects.filter(link=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Menu link already exists")
        else:
            # For creation
            if Menu.objects.filter(link=value).exists():
                raise serializers.ValidationError("Menu link already exists")
        return value
        
    def to_representation(self, instance):
        """Custom representation for frontend compatibility"""
        representation = super().to_representation(instance)
        return {
            'id': representation['id'],
            'title': representation['label'],  # Frontend expects 'title'
            'icon': representation['icon'],
            'link': representation['link'],
            'label': representation['label']  # Keep original for API consistency
        }


class RoleMenuSerializer(serializers.ModelSerializer):
    """Serializer for RoleMenu model with nested menu details"""
    
    menu_details = MenuSerializer(source='menu', read_only=True)
    role_name = serializers.CharField(source='role.role_name', read_only=True)
    
    class Meta:
        model = RoleMenu
        fields = ['id', 'role_name', 'menu_details', 'permissions']
        
    def to_representation(self, instance):
        """Custom representation for frontend menu structure"""
        representation = super().to_representation(instance)
        menu_data = representation['menu_details']
        
        return {
            'id': menu_data['id'],
            'title': menu_data['title'],
            'icon': menu_data['icon'], 
            'link': menu_data['link'],
            'permissions': representation['permissions'],
            'role': representation['role_name']
        }


class RoleMenuCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating RoleMenu assignments"""
    
    class Meta:
        model = RoleMenu
        fields = ['role', 'menu', 'permissions']
        
    def validate_permissions(self, value):
        """Validate permissions structure"""
        required_keys = ['read', 'write', 'edit', 'delete']
        
        if not isinstance(value, dict):
            raise serializers.ValidationError("Permissions must be a dictionary")
            
        for key in required_keys:
            if key not in value:
                raise serializers.ValidationError(f"Missing permission: {key}")
            if not isinstance(value[key], bool):
                raise serializers.ValidationError(f"Permission {key} must be boolean")
                
        return value