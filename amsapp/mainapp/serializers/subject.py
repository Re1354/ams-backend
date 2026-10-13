from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from ..models.subjects import Subject
from ..models.subjects_demartments import SubjectDepartment
from ..models.subject_faculty import SubjectFaculty
from ..models.faculty import Faculty


class SubjectSerializer(serializers.ModelSerializer):
    """Serializer for Subject model"""
    
    class Meta:
        model = Subject
        fields = ['id', 'subject_name']
        
    def validate_subject_name(self, value):
        """Validate subject name is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Subject.objects.filter(subject_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Subject name already exists")
        else:
            # For creation
            if Subject.objects.filter(subject_name=value).exists():
                raise serializers.ValidationError("Subject name already exists")
        return value


class SubjectDepartmentSerializer(serializers.ModelSerializer):
    """Serializer for SubjectDepartment model"""
    
    subjects = serializers.SerializerMethodField(read_only=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_id = serializers.IntegerField(source='department.id', read_only=True)
    
    class Meta:
        model = SubjectDepartment
        fields = ['id', 'department_id', 'department_name', 'subject_ids', 'subjects']
        
    @extend_schema_field(SubjectSerializer(many=True))
    def get_subjects(self, obj):
        """Get subject details from subject_ids"""
        if obj.subject_ids:
            subjects = Subject.objects.filter(id__in=obj.subject_ids)
            return SubjectSerializer(subjects, many=True).data
        return []


class SubjectDepartmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating SubjectDepartment model"""
    
    class Meta:
        model = SubjectDepartment
        fields = ['department', 'subject_ids']
        
    def validate_department(self, value):
        """Validate department exists and is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if SubjectDepartment.objects.filter(department=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Department already has a subject mapping")
        else:
            # For creation
            if SubjectDepartment.objects.filter(department=value).exists():
                raise serializers.ValidationError("Department already has a subject mapping")
        return value
        
    def validate_subject_ids(self, value):
        """Validate that all subject IDs exist"""
        if value:
            existing_subjects = Subject.objects.filter(id__in=value)
            existing_ids = list(existing_subjects.values_list('id', flat=True))
            
            for subject_id in value:
                if subject_id not in existing_ids:
                    raise serializers.ValidationError(f"Subject with ID {subject_id} does not exist")
        return value


class SubjectFacultySerializer(serializers.ModelSerializer):
    """Serializer for SubjectFaculty model"""
    
    subjects = serializers.SerializerMethodField(read_only=True)
    faculty_name = serializers.CharField(source='faculty.faculty_name', read_only=True)
    faculty_code = serializers.CharField(source='faculty.faculty_code', read_only=True)
    faculty_id = serializers.IntegerField(source='faculty.id', read_only=True)
    
    class Meta:
        model = SubjectFaculty
        fields = ['id', 'faculty_id', 'faculty_name', 'faculty_code', 'subject_ids', 'subjects']
        
    @extend_schema_field(SubjectSerializer(many=True))
    def get_subjects(self, obj):
        """Get subject details from subject_ids"""
        if obj.subject_ids:
            subjects = Subject.objects.filter(id__in=obj.subject_ids)
            return SubjectSerializer(subjects, many=True).data
        return []


class SubjectFacultyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating SubjectFaculty model"""
    
    class Meta:
        model = SubjectFaculty
        fields = ['faculty', 'subject_ids']
        
    def validate_faculty(self, value):
        """Validate faculty exists and is unique"""
        if self.instance:
            if SubjectFaculty.objects.filter(faculty=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Faculty already has a subject mapping")
        else:
            if SubjectFaculty.objects.filter(faculty=value).exists():
                raise serializers.ValidationError("Faculty already has a subject mapping")
        return value
        
    def validate_subject_ids(self, value):
        """Validate that all subject IDs exist and deduplicate"""
        if value:
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for item in value:
                if item not in seen:
                    seen.add(item)
                    deduped.append(item)
            
            existing_subjects = Subject.objects.filter(id__in=deduped)
            existing_ids = set(existing_subjects.values_list('id', flat=True))
            
            for subject_id in deduped:
                if subject_id not in existing_ids:
                    raise serializers.ValidationError(f"Subject with ID {subject_id} does not exist")
            return deduped
        return value or []
