from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User
from .tokens import CustomRefreshToken


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token serializer for our User model
    """
    
    @classmethod
    def get_token(cls, user):
        token = CustomRefreshToken.for_user(user)
        
        # Add custom claims
        token['username'] = user.username
        token['email'] = user.email
        if user.role:
            token['role'] = user.role.role_name
            token['role_id'] = user.role.id
        else:
            token['role'] = None
            token['role_id'] = None
        
        return token
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError('No active account found with the given credentials')
        
        from django.contrib.auth.hashers import check_password
        if not check_password(password, user.password):
            raise serializers.ValidationError('No active account found with the given credentials')
        
        refresh = self.get_token(user)
        
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }