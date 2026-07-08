from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email
from rest_framework import serializers
from ..models import Students, Submission, ExamQuestion, Exam
from ..utils import normalize_semester_value


ACADEMIC_TYPE_HSC = 'HSC'
ACADEMIC_TYPE_DIPLOMA = 'DIPLOMA'

# When a student is added without an email, the app stores this marker instead
# of a fabricated address, so the field is a plain CharField (not EmailField)
# that still validates real addresses. Keep this string in sync with the
# frontend NOT_ENTERED_EMAIL constant.
EMAIL_NOT_ENTERED = 'Not Entered'


def optional_email_field():
    """A student email field: optional, accepts the 'Not Entered' marker."""
    return serializers.CharField(required=False, allow_blank=True, max_length=254)


def validate_optional_email(value):
    """Allow blank or the 'Not Entered' marker; validate any real address."""
    if value is None:
        return value
    trimmed = value.strip()
    if trimmed in ('', EMAIL_NOT_ENTERED):
        return trimmed
    try:
        django_validate_email(trimmed)
    except DjangoValidationError:
        raise serializers.ValidationError('Enter a valid email address.')
    return trimmed


class OptionalEmailSerializerMixin:
    """Validate email, tolerating blank and the 'Not Entered' marker."""

    def validate_email(self, value):
        return validate_optional_email(value)


def validate_gpa_range(value, label, maximum):
    if value < 0:
        raise serializers.ValidationError(f"{label} cannot be negative")
    if value > maximum:
        raise serializers.ValidationError(f"{label} cannot be greater than {maximum:g}")
    return value


def normalize_academic_fields(serializer, data):
    academic_type = data.get(
        'academic_type',
        getattr(serializer.instance, 'academic_type', ACADEMIC_TYPE_HSC) if serializer.instance else ACADEMIC_TYPE_HSC,
    )
    academic_type = (academic_type or ACADEMIC_TYPE_HSC).upper()

    if academic_type not in {ACADEMIC_TYPE_HSC, ACADEMIC_TYPE_DIPLOMA}:
        raise serializers.ValidationError({
            'academic_type': 'Academic type must be HSC or DIPLOMA'
        })

    data['academic_type'] = academic_type
    if academic_type == ACADEMIC_TYPE_HSC:
        data['diploma'] = 0
    else:
        data['hsc'] = 0

    return data


class StudentsSerializer(OptionalEmailSerializerMixin, serializers.ModelSerializer):
    """Serializer for Students model"""

    email = optional_email_field()

    class Meta:
        model = Students
        fields = [
            'id', 'username', 'password', 'f_id', 'full_name', 'email',
            'department_shortname', 'registration_semester', 'created_at',
            'ssc', 'academic_type', 'hsc', 'diploma'
        ]
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
        """Validate SSC GPA is within the 5-point scale"""
        return validate_gpa_range(value, "SSC GPA", 5)
    
    def validate_hsc(self, value):
        """Validate HSC GPA is within the 5-point scale"""
        return validate_gpa_range(value, "HSC GPA", 5)
    
    def validate_diploma(self, value):
        """Validate Diploma CGPA is within the 4-point scale"""
        return validate_gpa_range(value, "Diploma CGPA", 4)

    def validate_registration_semester(self, value):
        """Validate registration semester is provided"""
        try:
            return normalize_semester_value(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, data):
        return normalize_academic_fields(self, data)


class StudentCreateSerializer(OptionalEmailSerializerMixin, serializers.ModelSerializer):
    """Serializer for creating students"""

    email = optional_email_field()

    class Meta:
        model = Students
        fields = [
            'username', 'password', 'f_id', 'full_name', 'email',
            'department_shortname', 'registration_semester', 'ssc',
            'academic_type', 'hsc', 'diploma'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def validate_username(self, value):
        """Validate username is unique"""
        if Students.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_ssc(self, value):
        """Validate SSC GPA is within the 5-point scale"""
        return validate_gpa_range(value, "SSC GPA", 5)
    
    def validate_hsc(self, value):
        """Validate HSC GPA is within the 5-point scale"""
        return validate_gpa_range(value, "HSC GPA", 5)
    
    def validate_diploma(self, value):
        """Validate Diploma CGPA is within the 4-point scale"""
        return validate_gpa_range(value, "Diploma CGPA", 4)

    def validate_registration_semester(self, value):
        """Validate registration semester is provided"""
        try:
            return normalize_semester_value(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, data):
        return normalize_academic_fields(self, data)


class StudentUpdateSerializer(OptionalEmailSerializerMixin, serializers.ModelSerializer):
    """Serializer for updating students"""

    email = optional_email_field()

    class Meta:
        model = Students
        fields = [
            'username', 'f_id', 'full_name', 'email',
            'department_shortname', 'registration_semester', 'ssc',
            'academic_type', 'hsc', 'diploma'
        ]
        # Note: Password update should be handled separately for security
    
    def validate_username(self, value):
        """Validate username is unique"""
        if self.instance and Students.objects.filter(username=value).exclude(id=self.instance.id).exists():
            raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_ssc(self, value):
        """Validate SSC GPA is within the 5-point scale"""
        return validate_gpa_range(value, "SSC GPA", 5)
    
    def validate_hsc(self, value):
        """Validate HSC GPA is within the 5-point scale"""
        return validate_gpa_range(value, "HSC GPA", 5)
    
    def validate_diploma(self, value):
        """Validate Diploma CGPA is within the 4-point scale"""
        return validate_gpa_range(value, "Diploma CGPA", 4)

    def validate_registration_semester(self, value):
        """Validate registration semester is provided"""
        try:
            return normalize_semester_value(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def validate(self, data):
        return normalize_academic_fields(self, data)


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
