from rest_framework import serializers

from ..models import AdmissionReportSignatory


class AdmissionReportSignatorySerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    department_name = serializers.CharField(
        source="department.department_name", read_only=True, allow_null=True
    )
    department_shortname = serializers.CharField(
        source="department.department_shortname", read_only=True, allow_null=True
    )
    faculty_name = serializers.CharField(
        source="faculty.faculty_name", read_only=True, allow_null=True
    )
    faculty_shortname = serializers.CharField(
        source="faculty.faculty_shortname", read_only=True, allow_null=True
    )
    affiliation_department_name = serializers.CharField(
        source="affiliation_department.department_name", read_only=True, allow_null=True
    )
    affiliation_department_shortname = serializers.CharField(
        source="affiliation_department.department_shortname", read_only=True, allow_null=True
    )

    class Meta:
        model = AdmissionReportSignatory
        fields = [
            "id",
            "role",
            "role_label",
            "name",
            "designation",
            "department",
            "department_name",
            "department_shortname",
            "affiliation_department",
            "affiliation_department_name",
            "affiliation_department_shortname",
            "faculty",
            "faculty_name",
            "faculty_shortname",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        role = attrs.get("role", getattr(self.instance, "role", None))
        department = attrs.get("department", getattr(self.instance, "department", None))
        faculty = attrs.get("faculty", getattr(self.instance, "faculty", None))
        affiliation_department = attrs.get(
            "affiliation_department",
            getattr(self.instance, "affiliation_department", None),
        )

        if role == AdmissionReportSignatory.ROLE_DEAN:
            if not faculty or department or affiliation_department:
                raise serializers.ValidationError(
                    "A dean must be mapped to one faculty only."
                )
        elif role in {
            AdmissionReportSignatory.ROLE_CONVENOR,
            AdmissionReportSignatory.ROLE_DEPARTMENT_HEAD,
        }:
            if not department or faculty:
                raise serializers.ValidationError(
                    "A convenor or department head must be mapped to one department only."
                )
            if (
                role == AdmissionReportSignatory.ROLE_DEPARTMENT_HEAD
                and affiliation_department
            ):
                raise serializers.ValidationError(
                    "A department head uses the report department as their affiliation."
                )
        return attrs
