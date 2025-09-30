from rest_framework import serializers
from ..models.subjects import Subject
from ..models.subjects_demartments import SubjectDepartment


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
