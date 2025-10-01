from rest_framework import serializers
from ..models.departments import Department


class DepartmentSerializer(serializers.ModelSerializer):
    """Serializer for Department model"""
    
    class Meta:
        model = Department
        fields = ['id', 'department_name', 'department_shortname']
        
    def validate_department_name(self, value):
        """Validate department name is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Department.objects.filter(department_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Department name already exists")
        else:
            # For creation
            if Department.objects.filter(department_name=value).exists():
                raise serializers.ValidationError("Department name already exists")
        return value


class DepartmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating Department model"""
    
    class Meta:
        model = Department
        fields = ['department_name', 'department_shortname']
        
    def validate_department_name(self, value):
        """Validate department name is unique and not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Department name cannot be empty")
            
        value = value.strip()
        
        if self.instance:
            # For updates, exclude the current instance
            if Department.objects.filter(department_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Department name already exists")
        else:
            # For creation
            if Department.objects.filter(department_name=value).exists():
                raise serializers.ValidationError("Department name already exists")
        return value
    
    def validate_department_shortname(self, value):
        """Validate department shortname is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Department shortname cannot be empty")
        return value.strip().upper()  # Convert to uppercase for consistency


class DepartmentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Department with user count"""
    
    user_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Department
        fields = ['id', 'department_name', 'department_shortname', 'user_count']
        
    def get_user_count(self, obj):
        """Get the number of users in this department"""
        return obj.users.count()