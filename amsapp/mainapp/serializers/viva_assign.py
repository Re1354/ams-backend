from rest_framework import serializers
from ..models.viva_assign import VivaAssignment
from ..models.students import Students
from ..models.user import User
from ..models.exam import Exam

class VivaAssignmentSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    teacher_username = serializers.CharField(source='teacher.username', read_only=True)
    exam_name = serializers.CharField(source='exam.exam_name', read_only=True)

    class Meta:
        model = VivaAssignment
        fields = [
            'id', 'student', 'student_username', 'teacher', 'teacher_username',
            'exam', 'exam_name', 'scheduled_at', 'time', 'room', 'total_marks',
            'rubric_snapshot', 'rubric_scores', 'remarks', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class VivaAssignmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VivaAssignment
        fields = ['student', 'teacher', 'exam', 'scheduled_at', 'time', 'room']

    def validate(self, data):
        # Ensure unique together constraint
        if VivaAssignment.objects.filter(student=data['student'], teacher=data['teacher'], exam=data['exam']).exists():
            raise serializers.ValidationError('This viva assignment already exists.')
        return data

class VivaAssignmentBulkCreateSerializer(serializers.Serializer):
    assignments = VivaAssignmentCreateSerializer(many=True)

    def validate(self, data):
        # Check for duplicates in the bulk payload
        seen = set()
        for item in data['assignments']:
            key = (item['student'].id, item['teacher'].id, item['exam'].id)
            if key in seen:
                raise serializers.ValidationError('Duplicate assignment in payload.')
            seen.add(key)
        # Check for existing assignments in DB
        for item in data['assignments']:
            if VivaAssignment.objects.filter(student=item['student'], teacher=item['teacher'], exam=item['exam']).exists():
                raise serializers.ValidationError(f"Assignment already exists for student {item['student'].id}, teacher {item['teacher'].id}, exam {item['exam'].id}")
        return data
