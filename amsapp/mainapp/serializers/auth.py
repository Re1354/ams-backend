from rest_framework import serializers
from django.contrib.auth.hashers import check_password, make_password
from ..models import User, Role, Department
from .departments import DepartmentSerializer


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model"""
    
    class Meta:
        model = Role
        fields = ['id', 'role_name']
        
    def validate_role_name(self, value):
        """Validate role name is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Role.objects.filter(role_name=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Role name already exists")
        else:
            # For creation
            if Role.objects.filter(role_name=value).exists():
                raise serializers.ValidationError("Role name already exists")
        return value


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model with role and department details"""
    
    role_name = serializers.CharField(source='role.role_name', read_only=True)
    role_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    department_name = serializers.CharField(source='department.department_name', read_only=True)
    department_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'role_id', 'role_name', 'department_id', 'department_name', 'created_at']
        read_only_fields = ['id', 'created_at', 'role_name', 'department_name']
        extra_kwargs = {
            'password': {'write_only': True}
        }
    
    def validate_username(self, value):
        """Validate username is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if User.objects.filter(username=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Username already exists")
        else:
            # For creation
            if User.objects.filter(username=value).exists():
                raise serializers.ValidationError("Username already exists")
        return value
    
    def validate_email(self, value):
        """Validate email is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if User.objects.filter(email=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Email already exists")
        else:
            # For creation
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email already exists")
        return value
    
    def validate_role_id(self, value):
        """Validate role exists"""
        if value is not None:
            try:
                Role.objects.get(id=value)
            except Role.DoesNotExist:
                raise serializers.ValidationError("Role does not exist")
        return value
    
    def validate_department_id(self, value):
        """Validate department exists"""
        if value is not None:
            try:
                Department.objects.get(id=value)
            except Department.DoesNotExist:
                raise serializers.ValidationError("Department does not exist")
        return value
    
    def create(self, validated_data):
        """Create user with hashed password"""
        role_id = validated_data.pop('role_id', None)
        department_id = validated_data.pop('department_id', None)
        password = validated_data.pop('password')
        
        # Hash password
        validated_data['password'] = make_password(password)
        
        # Create user
        user = User.objects.create(**validated_data)
        
        # Set role if provided
        if role_id:
            role = Role.objects.get(id=role_id)
            user.role = role
        
        # Set department if provided
        if department_id:
            department = Department.objects.get(id=department_id)
            user.department = department
        
        if role_id or department_id:
            user.save()
        
        return user
    
    def update(self, instance, validated_data):
        """Update user with hashed password if provided"""
        role_id = validated_data.pop('role_id', None)
        department_id = validated_data.pop('department_id', None)
        password = validated_data.pop('password', None)
        
        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # Update password if provided
        if password:
            instance.password = make_password(password)
        
        # Update role if provided
        if role_id is not None:
            if role_id == 0:  # Allow setting role to null
                instance.role = None
            else:
                role = Role.objects.get(id=role_id)
                instance.role = role
        
        # Update department if provided
        if department_id is not None:
            if department_id == 0:  # Allow setting department to null
                instance.department = None
            else:
                department = Department.objects.get(id=department_id)
                instance.department = department
        
        instance.save()
        return instance


class LoginSerializer(serializers.Serializer):
    """Serializer for user login"""
    
    username = serializers.CharField(max_length=100)
    password = serializers.CharField(max_length=255, write_only=True)
    
    def validate(self, data):
        """Validate user credentials"""
        username = data.get('username')
        password = data.get('password')
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials")
        
        if not check_password(password, user.password):
            raise serializers.ValidationError("Invalid credentials")
        
        data['user'] = user
        return data


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for user with role and department information"""
    
    role_details = RoleSerializer(source='role', read_only=True)
    department_details = DepartmentSerializer(source='department', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'created_at', 'role_details', 'department_details']
        read_only_fields = ['id', 'username', 'email', 'created_at']
