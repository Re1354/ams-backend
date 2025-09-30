from rest_framework import serializers
from ..models import Menu, RoleMenu, Role


class MenuSerializer(serializers.ModelSerializer):
    """Serializer for Menu model"""
    
    class Meta:
        model = Menu
        fields = ['id', 'label', 'icon', 'link', 'component']
        
    def validate_label(self, value):
        """Validate menu label is unique"""
        if self.instance:
            # For updates, exclude the current instance
            if Menu.objects.filter(label=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Menu label already exists")
        else:
            # For creation
            if Menu.objects.filter(label=value).exists():
                raise serializers.ValidationError("Menu label already exists")
        return value
    
    def validate_link(self, value):
        """Validate menu link format and uniqueness"""
        # Ensure link starts with /
        if not value.startswith('/'):
            value = '/' + value
            
        # Check uniqueness
        if self.instance:
            # For updates, exclude the current instance
            if Menu.objects.filter(link=value).exclude(id=self.instance.id).exists():
                raise serializers.ValidationError("Menu link already exists")
        else:
            # For creation
            if Menu.objects.filter(link=value).exists():
                raise serializers.ValidationError("Menu link already exists")
        return value
        
    def to_representation(self, instance):
        """Custom representation for frontend compatibility"""
        representation = super().to_representation(instance)
        return {
            'id': representation['id'],
            'title': representation['label'],  # Frontend expects 'title'
            'icon': representation['icon'],
            'link': representation['link'],
            'label': representation['label']  # Keep original for API consistency
        }


class RoleMenuSerializer(serializers.ModelSerializer):
    """Serializer for RoleMenu model with nested menu details"""
    
    menu_details = MenuSerializer(source='menu', read_only=True)
    role_name = serializers.CharField(source='role.role_name', read_only=True)
    
    class Meta:
        model = RoleMenu
        fields = ['id', 'role_name', 'menu_details', 'permissions']
        
    def to_representation(self, instance):
        """Custom representation for frontend menu structure"""
        representation = super().to_representation(instance)
        menu_data = representation['menu_details']
        
        return {
            'id': menu_data['id'],
            'title': menu_data['title'],
            'icon': menu_data['icon'], 
            'link': menu_data['link'],
            'permissions': representation['permissions'],
            'role': representation['role_name']
        }


class RoleMenuCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating RoleMenu assignments"""
    
    class Meta:
        model = RoleMenu
        fields = ['role', 'menu', 'permissions']
        
    def validate_permissions(self, value):
        """Validate permissions structure"""
        required_keys = ['read', 'write', 'edit', 'delete']
        
        if not isinstance(value, dict):
            raise serializers.ValidationError("Permissions must be a dictionary")
            
        for key in required_keys:
            if key not in value:
                raise serializers.ValidationError(f"Missing permission: {key}")
            if not isinstance(value[key], bool):
                raise serializers.ValidationError(f"Permission {key} must be boolean")
                
        return value
