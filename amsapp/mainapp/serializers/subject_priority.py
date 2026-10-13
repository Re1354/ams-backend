from rest_framework import serializers
from ..models import Department, Subject, SubjectPriority


class SubjectPriorityItemSerializer(serializers.ModelSerializer):
    subject_id = serializers.IntegerField(source="subject.id")
    subject_name = serializers.CharField(source="subject.subject_name")

    class Meta:
        model = SubjectPriority
        fields = ["id", "subject_id", "subject_name", "priority"]


class DepartmentSubjectPrioritySerializer(serializers.Serializer):
    department_id = serializers.IntegerField()
    department_name = serializers.CharField()
    department_shortname = serializers.CharField()
    priorities = SubjectPriorityItemSerializer(many=True)


class SubjectPrioritySaveSerializer(serializers.Serializer):
    department_id = serializers.IntegerField(required=True)
    subject_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=True,
        help_text="Ordered list of subject IDs from highest (priority 1) to lowest priority.",
    )

    def validate_department_id(self, value):
        if not Department.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Department with ID {value} does not exist.")
        return value

    def validate_subject_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate subjects are not allowed in the priority list.")
        if value:
            existing_count = Subject.objects.filter(id__in=value).count()
            if existing_count != len(value):
                raise serializers.ValidationError("One or more subject IDs are invalid or do not exist.")
        return value
