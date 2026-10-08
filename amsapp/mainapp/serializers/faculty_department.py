from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
# pyrefly: ignore [missing-import]
from ..models.departments import Department
# pyrefly: ignore [missing-import]
from ..models.faculties_departments import FacultyDepartment
from .departments import DepartmentSerializer


class DepartmentSummarySerializer(serializers.ModelSerializer):
    """Summary serializer for Department model in FacultyDepartment mappings"""
    class Meta:
        model = Department
        fields = ['id', 'department_name', 'department_shortname']


class FacultyDepartmentSerializer(serializers.ModelSerializer):
    """Serializer for FacultyDepartment model"""

    departments = serializers.SerializerMethodField(read_only=True)
    faculty_name = serializers.CharField(source='faculty.faculty_name', read_only=True)
    faculty_shortname = serializers.CharField(source='faculty.faculty_shortname', read_only=True)
    faculty_id = serializers.IntegerField(source='faculty.id', read_only=True)

    class Meta:
        model = FacultyDepartment
        fields = ['id', 'faculty_id', 'faculty_name', 'faculty_shortname', 'department_ids', 'departments']

    @extend_schema_field(DepartmentSummarySerializer(many=True))
    def get_departments(self, obj):
        """Get department details from department_ids"""
        if obj.department_ids:
            departments = Department.objects.filter(id__in=obj.department_ids).order_by('department_name')
            return DepartmentSummarySerializer(departments, many=True).data
        return []


class FacultyDepartmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating FacultyDepartment model"""

    class Meta:
        model = FacultyDepartment
        fields = ['faculty', 'department_ids']

    def validate_faculty(self, value):
        """Validate faculty exists and is unique"""
        if self.instance:
            # For updates, exclude current instance
            if FacultyDepartment.objects.filter(faculty=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Faculty already has a department mapping")
        else:
            # For creation
            if FacultyDepartment.objects.filter(faculty=value).exists():
                raise serializers.ValidationError("Faculty already has a department mapping")
        return value

    def validate_department_ids(self, value):
        """Validate that all department IDs exist"""
        if value:
            existing_departments = Department.objects.filter(id__in=value)
            existing_ids = set(existing_departments.values_list('id', flat=True))

            for dept_id in value:
                if dept_id not in existing_ids:
                    raise serializers.ValidationError(f"Department with ID {dept_id} does not exist")
        return value
