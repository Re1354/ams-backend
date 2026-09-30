from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email
from rest_framework import serializers
from ..models import Students, Submission, ExamQuestion, Exam, Faculty, Department, FacultyDepartment
from ..utils import normalize_semester_value


ACADEMIC_TYPE_HSC = 'HSC'
ACADEMIC_TYPE_DIPLOMA = 'DIPLOMA'

# When a student is added without an email, the app stores this marker instead
# of a fabricated address, so the field is a plain CharField (not EmailField)
# that still validates real addresses. Keep this string in sync with the
# frontend NOT_ENTERED_EMAIL constant.
EMAIL_NOT_ENTERED = 'Not Entered'

MAX_DEPARTMENT_CHOICES = 3


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


def validate_department_choices(faculty, department_choices):
    """
    Validate department_choices list against selected faculty.

    Rules:
    - Maximum MAX_DEPARTMENT_CHOICES items.
    - No duplicates.
    - Each department must exist.
    - Each department must belong to the selected faculty.
    - Priority must be sequential starting at 1.
    """
    if not department_choices:
        return []

    if len(department_choices) > MAX_DEPARTMENT_CHOICES:
        raise serializers.ValidationError(
            f"A maximum of {MAX_DEPARTMENT_CHOICES} department choices are allowed."
        )

    if department_choices and faculty is None:
        raise serializers.ValidationError(
            "A faculty must be selected before selecting department choices."
        )

    seen_dept_ids = set()
    seen_priorities = set()

    for idx, choice in enumerate(department_choices):
        if not isinstance(choice, dict):
            raise serializers.ValidationError(
                f"Choice at position {idx + 1} must be an object with 'department_id' and 'priority'."
            )

        dept_id = choice.get('department_id')
        priority = choice.get('priority')

        if dept_id is None or priority is None:
            raise serializers.ValidationError(
                f"Choice at position {idx + 1} must have 'department_id' and 'priority'."
            )

        try:
            dept_id = int(dept_id)
            priority = int(priority)
        except (ValueError, TypeError):
            raise serializers.ValidationError(
                f"Choice at position {idx + 1}: 'department_id' and 'priority' must be integers."
            )

        if dept_id in seen_dept_ids:
            raise serializers.ValidationError(
                f"Duplicate department choice: department_id {dept_id} appears more than once."
            )
        if priority in seen_priorities:
            raise serializers.ValidationError(
                f"Duplicate priority value {priority}."
            )

        seen_dept_ids.add(dept_id)
        seen_priorities.add(priority)

    # Validate sequential priorities starting at 1
    expected_priorities = set(range(1, len(department_choices) + 1))
    if seen_priorities != expected_priorities:
        raise serializers.ValidationError(
            "Priorities must be sequential starting from 1 (e.g. 1, 2, 3)."
        )

    # Validate all departments exist
    existing_dept_ids = set(
        Department.objects.filter(id__in=seen_dept_ids).values_list('id', flat=True)
    )
    missing = seen_dept_ids - existing_dept_ids
    if missing:
        raise serializers.ValidationError(
            f"The following department IDs do not exist: {sorted(missing)}"
        )

    # Validate departments belong to the selected faculty
    if faculty is not None:
        try:
            faculty_mapping = FacultyDepartment.objects.get(faculty=faculty)
            allowed_dept_ids = set(faculty_mapping.department_ids)
        except FacultyDepartment.DoesNotExist:
            allowed_dept_ids = set()

        not_in_faculty = seen_dept_ids - allowed_dept_ids
        if not_in_faculty:
            raise serializers.ValidationError(
                f"The following department IDs do not belong to the selected faculty: {sorted(not_in_faculty)}"
            )

    # Normalise: ensure both fields are ints, return sorted by priority
    normalised = sorted(
        [{'department_id': int(c['department_id']), 'priority': int(c['priority'])} for c in department_choices],
        key=lambda c: c['priority'],
    )
    return normalised


class DepartmentChoiceField(serializers.Field):
    """Serializer field for the department_choices JSON list."""

    def to_representation(self, value):
        if not isinstance(value, list) or not value:
            return []

        dept_ids = [
            c.get('department_id')
            for c in value
            if isinstance(c, dict) and c.get('department_id') is not None
        ]
        dept_map = {
            d.id: d
            for d in Department.objects.filter(id__in=dept_ids)
        }

        enriched = []
        for c in value:
            if not isinstance(c, dict):
                continue
            dept_id = c.get('department_id')
            dept = dept_map.get(dept_id)
            enriched.append({
                'department_id': dept_id,
                'priority': c.get('priority'),
                'department_name': dept.department_name if dept else c.get('department_name'),
                'department_shortname': dept.department_shortname if dept else c.get('department_shortname'),
            })
        return sorted(enriched, key=lambda x: x.get('priority') or 0)

    def to_internal_value(self, data):
        if not isinstance(data, list):
            raise serializers.ValidationError("department_choices must be a list.")
        return data


class StudentsSerializer(OptionalEmailSerializerMixin, serializers.ModelSerializer):
    """Serializer for Students model"""

    email = optional_email_field()
    faculty_id = serializers.IntegerField(source='faculty.id', read_only=True, allow_null=True)
    faculty_name = serializers.CharField(source='faculty.faculty_name', read_only=True, allow_null=True)
    department_choices = DepartmentChoiceField(required=False)

    class Meta:
        model = Students
        fields = [
            'id', 'username', 'password', 'f_id', 'full_name', 'email',
            'department_shortname', 'registration_semester', 'created_at',
            'ssc', 'academic_type', 'hsc', 'diploma',
            'faculty_id', 'faculty_name', 'department_choices',
        ]
        read_only_fields = ['id', 'created_at', 'faculty_id', 'faculty_name']
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
    faculty_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    department_choices = DepartmentChoiceField(required=False)

    class Meta:
        model = Students
        fields = [
            'username', 'password', 'f_id', 'full_name', 'email',
            'department_shortname', 'registration_semester', 'ssc',
            'academic_type', 'hsc', 'diploma',
            'faculty_id', 'department_choices',
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
        data = normalize_academic_fields(self, data)

        # Resolve faculty_id → Faculty instance
        faculty_id = data.pop('faculty_id', None)
        faculty = None
        if faculty_id is not None:
            try:
                faculty = Faculty.objects.get(id=faculty_id)
            except Faculty.DoesNotExist:
                raise serializers.ValidationError({'faculty_id': f"Faculty with id {faculty_id} does not exist."})
        data['faculty'] = faculty

        # Validate department_choices against the resolved faculty
        department_choices = data.get('department_choices', [])
        data['department_choices'] = validate_department_choices(faculty, department_choices)

        # Sync department_shortname with priority 1 choice if choices provided
        if data['department_choices']:
            first_choice = next((c for c in data['department_choices'] if c['priority'] == 1), None)
            if first_choice:
                dept = Department.objects.filter(id=first_choice['department_id']).first()
                if dept:
                    data['department_shortname'] = dept.department_shortname

        return data


class StudentUpdateSerializer(OptionalEmailSerializerMixin, serializers.ModelSerializer):
    """Serializer for updating students"""

    email = optional_email_field()
    faculty_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    department_choices = DepartmentChoiceField(required=False)

    class Meta:
        model = Students
        fields = [
            'username', 'f_id', 'full_name', 'email',
            'department_shortname', 'registration_semester', 'ssc',
            'academic_type', 'hsc', 'diploma',
            'faculty_id', 'department_choices',
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
        data = normalize_academic_fields(self, data)

        # Resolve faculty_id → Faculty instance (only when provided in the patch)
        if 'faculty_id' in data:
            faculty_id = data.pop('faculty_id')
            faculty = None
            if faculty_id is not None:
                try:
                    faculty = Faculty.objects.get(id=faculty_id)
                except Faculty.DoesNotExist:
                    raise serializers.ValidationError({'faculty_id': f"Faculty with id {faculty_id} does not exist."})
            data['faculty'] = faculty
        else:
            # Keep existing faculty for validation of department_choices
            faculty = self.instance.faculty if self.instance else None

        # If faculty was explicitly updated and department_choices wasn't provided, reset choices
        if 'faculty' in data and 'department_choices' not in data:
            if self.instance and self.instance.faculty != data['faculty']:
                data['department_choices'] = []

        # Validate department_choices against the (potentially new) faculty
        if 'department_choices' in data:
            resolved_faculty = data.get('faculty', faculty)
            data['department_choices'] = validate_department_choices(resolved_faculty, data['department_choices'])
            if data['department_choices']:
                first_choice = next((c for c in data['department_choices'] if c['priority'] == 1), None)
                if first_choice:
                    dept = Department.objects.filter(id=first_choice['department_id']).first()
                    if dept:
                        data['department_shortname'] = dept.department_shortname

        return data


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
