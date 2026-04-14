from rest_framework import serializers
from ..models import StudentAssignTeacherExam, Students, User, Exam, ExamSchedule


class StudentAssignTeacherExamSerializer(serializers.ModelSerializer):
    """Serializer for StudentAssignTeacherExam model"""
    
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_full_name = serializers.CharField(source='student.full_name', read_only=True)
    student_f_id = serializers.CharField(source='student.f_id', read_only=True)
    student_registration_semester = serializers.CharField(source='student.registration_semester', read_only=True)
    teacher_username = serializers.CharField(source='teacher.username', read_only=True)
    exam_department = serializers.CharField(source='exam.department', read_only=True)
    exam_semester = serializers.CharField(source='exam.semester', read_only=True)
    schedule_exam_date = serializers.DateTimeField(source='schedule.exam_date', read_only=True)
    schedule_duration = serializers.IntegerField(source='schedule.duration_minutes', read_only=True)
    
    class Meta:
        model = StudentAssignTeacherExam
        fields = [
            'id', 'student', 'teacher', 'exam', 'schedule', 'created_at',
            'student_username', 'student_full_name', 'student_f_id', 'student_registration_semester',
            'teacher_username', 'exam_department', 'exam_semester',
            'schedule_exam_date', 'schedule_duration'
        ]
        read_only_fields = ['id', 'created_at', 'student_username', 'student_full_name', 
                           'student_f_id', 'student_registration_semester', 'teacher_username',
                           'exam_department', 'exam_semester', 'schedule_exam_date', 'schedule_duration']


class StudentAssignBulkSerializer(serializers.Serializer):
    """Serializer for bulk assignment of students to teacher and exam"""
    
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        help_text="List of student IDs to assign"
    )
    teacher_id = serializers.IntegerField(help_text="Teacher ID who is assigning the exam")
    schedule_id = serializers.IntegerField(help_text="Schedule ID for the exam (exam_id will be automatically retrieved from schedule)")
    
    def validate_student_ids(self, value):
        """Validate that all student IDs exist"""
        existing_ids = Students.objects.filter(id__in=value).values_list('id', flat=True)
        missing_ids = set(value) - set(existing_ids)
        if missing_ids:
            raise serializers.ValidationError(f"Students with IDs {list(missing_ids)} do not exist")
        return value
    
    def validate_teacher_id(self, value):
        """Validate that teacher exists"""
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("Teacher does not exist")
        return value
    
    def validate_schedule_id(self, value):
        """Validate that schedule exists and has an associated exam"""
        try:
            schedule = ExamSchedule.objects.select_related('exam').get(id=value)
            if not schedule.exam:
                raise serializers.ValidationError("Schedule does not have an associated exam")
        except ExamSchedule.DoesNotExist:
            raise serializers.ValidationError("Schedule does not exist")
        return value


class StudentAssignSingleSerializer(serializers.Serializer):
    """Serializer for single student assignment to teacher and exam"""
    
    student_id = serializers.IntegerField(help_text="Student ID to assign")
    teacher_id = serializers.IntegerField(help_text="Teacher ID who is assigning the exam")
    schedule_id = serializers.IntegerField(help_text="Schedule ID for the exam (exam_id will be automatically retrieved from schedule)")
    
    def validate_student_id(self, value):
        """Validate that student exists"""
        if not Students.objects.filter(id=value).exists():
            raise serializers.ValidationError("Student does not exist")
        return value
    
    def validate_teacher_id(self, value):
        """Validate that teacher exists"""
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("Teacher does not exist")
        return value
    
    def validate_schedule_id(self, value):
        """Validate that schedule exists and has an associated exam"""
        try:
            schedule = ExamSchedule.objects.select_related('exam').get(id=value)
            if not schedule.exam:
                raise serializers.ValidationError("Schedule does not have an associated exam")
        except ExamSchedule.DoesNotExist:
            raise serializers.ValidationError("Schedule does not exist")
        return value
