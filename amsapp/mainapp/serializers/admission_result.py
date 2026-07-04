from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from ..models import AdmissionConfiguration, AdmissionResult, Department, Exam, VivaAssignment
from ..models.viva_marks import VivaMarks
from ..utils import normalize_semester_value


class AdmissionConfigurationSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.department_name", read_only=True)
    department_shortname = serializers.CharField(
        source="department.department_shortname",
        read_only=True,
    )
    exam_department = serializers.CharField(source="exam.department", read_only=True)

    class Meta:
        model = AdmissionConfiguration
        fields = [
            "id",
            "department",
            "department_name",
            "department_shortname",
            "semester",
            "exam",
            "exam_department",
            "seat_limit",
            "waiting_student_limit",
            "threshold",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_threshold(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Threshold must be between 0 and 100")
        return value

    def validate_semester(self, value):
        try:
            return normalize_semester_value(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))


class AdmissionConfigurationUpsertSerializer(serializers.Serializer):
    department_id = serializers.IntegerField(required=False)
    exam_id = serializers.IntegerField(required=False)
    semester = serializers.CharField(required=False)
    seat_limit = serializers.IntegerField(required=False, min_value=0)
    waiting_student_limit = serializers.IntegerField(required=False, min_value=0)
    threshold = serializers.FloatField(required=False, min_value=0.0, max_value=100.0)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        exam_id = attrs.get("exam_id")
        department_id = attrs.get("department_id")
        semester = attrs.get("semester")

        if semester is not None:
            try:
                attrs["semester"] = normalize_semester_value(semester)
            except ValueError as exc:
                raise serializers.ValidationError({"semester": str(exc)})

        if self.partial:
            if exam_id and not Exam.objects.filter(id=exam_id).exists():
                raise serializers.ValidationError({"exam_id": "Exam does not exist"})
            if department_id and not Department.objects.filter(id=department_id).exists():
                raise serializers.ValidationError({"department_id": "Department does not exist"})
            return attrs

        if not exam_id and not (department_id and semester):
            raise serializers.ValidationError(
                "Provide exam_id or both department_id and semester."
            )

        if exam_id and not Exam.objects.filter(id=exam_id).exists():
            raise serializers.ValidationError({"exam_id": "Exam does not exist"})

        if department_id and not Department.objects.filter(id=department_id).exists():
            raise serializers.ValidationError({"department_id": "Department does not exist"})

        return attrs


class AdmissionResultSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source="student.username", read_only=True)
    student_full_name = serializers.CharField(source="student.full_name", read_only=True)
    student_f_id = serializers.CharField(source="student.f_id", read_only=True)
    student_registration_semester = serializers.CharField(
        source="student.registration_semester",
        read_only=True,
    )
    student_ssc = serializers.FloatField(source="student.ssc", read_only=True)
    student_academic_type = serializers.CharField(
        source="student.academic_type",
        read_only=True,
    )
    student_hsc = serializers.FloatField(source="student.hsc", read_only=True)
    student_diploma = serializers.FloatField(source="student.diploma", read_only=True)
    department_name = serializers.CharField(source="department.department_name", read_only=True)
    department_shortname = serializers.CharField(
        source="department.department_shortname",
        read_only=True,
    )
    configuration_details = AdmissionConfigurationSerializer(
        source="configuration",
        read_only=True,
    )
    exam_details = serializers.SerializerMethodField()
    viva_marks_entered = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionResult
        fields = [
            "id",
            "exam",
            "student",
            "student_username",
            "student_full_name",
            "student_f_id",
            "student_registration_semester",
            "student_ssc",
            "student_academic_type",
            "student_hsc",
            "student_diploma",
            "configuration",
            "configuration_details",
            "department",
            "department_name",
            "department_shortname",
            "mcq_marks",
            "viva_marks",
            "viva_marks_entered",
            "viva_given",
            "written_viva_total",
            "total_marks",
            "weighted_total_marks",
            "attended_exam",
            "subject_wise_marks",
            "is_selected",
            "is_override_accepted",
            "is_admitted",
            "result_status",
            "status",
            "threshold_applied",
            "remarks",
            "ssc_score",
            "academic_score",
            "academic_source",
            "ssc_contribution",
            "academic_contribution",
            "written_contribution",
            "viva_contribution",
            "exam_details",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "total_marks",
            "written_viva_total",
            "weighted_total_marks",
        ]

    @extend_schema_field(serializers.DictField())
    def get_exam_details(self, obj):
        return {
            "id": obj.exam.id,
            "department": obj.exam.department,
            "semester": obj.exam.semester,
            "total_marks": obj.exam.total_marks,
        }

    @extend_schema_field(serializers.BooleanField())
    def get_viva_marks_entered(self, obj):
        viva_assignment = (
            VivaAssignment.objects.filter(student=obj.student, exam=obj.exam)
            .order_by("-updated_at", "-created_at", "-id")
            .first()
        )
        if viva_assignment:
            return bool(
                viva_assignment.rubric_scores
                or viva_assignment.remarks
                or float(viva_assignment.total_marks or 0) != 0
                or VivaMarks.objects.filter(student=obj.student).exists()
            )

        return VivaMarks.objects.filter(student=obj.student).exists()


class CalculateAdmissionResultsSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField(help_text="Exam ID for which to calculate admission results")

    def validate_exam_id(self, value):
        if not Exam.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Exam with ID {value} does not exist")
        return value


class CalculateResultsResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    message = serializers.CharField()
    processed_count = serializers.IntegerField()
    selected_count = serializers.IntegerField()
    not_selected_count = serializers.IntegerField()
    exam_id = serializers.IntegerField()
    configuration_id = serializers.IntegerField(required=False)
    status_counts = serializers.DictField(required=False)


class AdmissionResultFilterSerializer(serializers.Serializer):
    exam_id = serializers.IntegerField(required=False)
    configuration_id = serializers.IntegerField(required=False)
    department_id = serializers.IntegerField(required=False)
    student_id = serializers.IntegerField(required=False)
    semester = serializers.CharField(required=False)
    search = serializers.CharField(required=False)
    is_selected = serializers.BooleanField(required=False)
    attended_exam = serializers.BooleanField(required=False)
    status = serializers.ChoiceField(
        choices=["PENDING", "PUBLISHED", "CANCELLED"],
        required=False,
    )
    result_status = serializers.ChoiceField(
        choices=["SELECTED", "WAITING", "REJECTED", "ABSENT"],
        required=False,
    )
    sort_by = serializers.ChoiceField(
        choices=["name", "score", "form_id", "serial"],
        required=False,
    )
    order = serializers.ChoiceField(
        choices=["asc", "desc"],
        required=False,
    )


class BulkAdmissionStatusUpdateSerializer(serializers.Serializer):
    configuration_id = serializers.IntegerField(required=False)
    exam_id = serializers.IntegerField(required=False)
    action = serializers.ChoiceField(
        choices=["SET_STATUS", "SET_ADMITTED", "REVERT_TO_STORED_STATUS"],
        required=False,
        default="SET_STATUS",
    )
    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
    )
    result_status = serializers.ChoiceField(
        choices=["SELECTED", "WAITING", "REJECTED"],
        required=False,
    )

    def validate(self, attrs):
        if not attrs.get("configuration_id") and not attrs.get("exam_id"):
            raise serializers.ValidationError(
                "Provide configuration_id or exam_id to update candidate status."
            )

        if attrs.get("action", "SET_STATUS") == "SET_STATUS" and not attrs.get("result_status"):
            raise serializers.ValidationError(
                {"result_status": "result_status is required when action is SET_STATUS."}
            )
        return attrs
