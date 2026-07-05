from rest_framework import serializers
from ..models.viva_assign import VivaAssignment
from ..models.students import Students
from ..models.user import User
from ..models.exam import Exam

class VivaAssignmentSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_full_name = serializers.CharField(source='student.full_name', read_only=True)
    student_f_id = serializers.CharField(source='student.f_id', read_only=True)
    student_registration_semester = serializers.CharField(source='student.registration_semester', read_only=True)
    student_department_shortname = serializers.CharField(source='student.department_shortname', read_only=True)
    teacher_username = serializers.CharField(source='teacher.username', read_only=True)
    exam_name = serializers.SerializerMethodField()
    exam_details = serializers.SerializerMethodField()

    class Meta:
        model = VivaAssignment
        fields = [
            'id', 'student', 'student_username', 'student_name', 'student_full_name',
            'student_f_id', 'student_registration_semester', 'student_department_shortname',
            'teacher', 'teacher_username', 'exam', 'exam_name', 'exam_details',
            'scheduled_at', 'time', 'room', 'total_marks', 'rubric_snapshot',
            'rubric_scores', 'remarks', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        if obj.student:
            return obj.student.full_name or obj.student.username
        return None

    def get_exam_name(self, obj):
        if obj.exam:
            return f"{obj.exam.department} - {obj.exam.semester}"
        return None

    def get_exam_details(self, obj):
        if not obj.exam:
            return None

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
            'department_shortnames': department_shortnames,
            'created_at': obj.exam.created_at,
            'updated_at': obj.exam.updated_at,
        }

class VivaAssignmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VivaAssignment
        fields = ['student', 'teacher', 'exam', 'scheduled_at', 'time', 'room']

    def validate(self, data):
        # Ensure unique together constraint
        if VivaAssignment.objects.filter(student=data['student'], teacher=data['teacher'], exam=data['exam']).exists():
            raise serializers.ValidationError({
                'assignment': (
                    f"Viva assignment already exists for student "
                    f"{data['student'].id}, teacher {data['teacher'].id}, "
                    f"exam {data['exam'].id}."
                )
            })
        return data

class VivaAssignmentBulkCreateSerializer(serializers.Serializer):
    assignments = VivaAssignmentCreateSerializer(many=True)

    def validate(self, data):
        # Check for duplicates in the bulk payload
        seen = set()
        for item in data['assignments']:
            key = (item['student'].id, item['teacher'].id, item['exam'].id)
            if key in seen:
                raise serializers.ValidationError({
                    'assignments': (
                        f"Duplicate assignment in payload for student {item['student'].id}, "
                        f"teacher {item['teacher'].id}, exam {item['exam'].id}."
                    )
                })
            seen.add(key)
        # Check for existing assignments in DB
        duplicate_messages = []
        for item in data['assignments']:
            if VivaAssignment.objects.filter(student=item['student'], teacher=item['teacher'], exam=item['exam']).exists():
                duplicate_messages.append(
                    f"student {item['student'].id}, teacher {item['teacher'].id}, exam {item['exam'].id}"
                )
        if duplicate_messages:
            raise serializers.ValidationError({
                'assignments': (
                    "Viva assignment already exists for "
                    + "; ".join(duplicate_messages)
                    + "."
                )
            })
        return data
