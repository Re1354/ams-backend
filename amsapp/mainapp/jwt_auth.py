from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import serializers
from django.contrib.auth.hashers import check_password
from .models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'username'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove default fields
        self.fields.pop('username', None)
        self.fields.pop('password', None)
        
        # Add our custom fields
        self.fields['username'] = serializers.CharField()
        self.fields['password'] = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        # Get credentials
        username = attrs.get('username')
        password = attrs.get('password')
        
        if not username or not password:
            raise serializers.ValidationError('Username and password are required')
        
        # Authenticate against our custom User model
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid credentials')
        
        if not check_password(password, user.password):
            raise serializers.ValidationError('Invalid credentials')
        
        # Create a mock Django user for JWT token generation
        class MockUser:
            def __init__(self, pk, username):
                self.pk = pk
                self.id = pk
                self.username = username
                self.is_active = True
        
        mock_user = MockUser(user.id, user.username)
        
        # Store our real user for later use
        self.user = user
        
        # Generate token using mock user
        refresh = self.get_token(mock_user)
        
        return {
            'refresh': refresh,
            'access': refresh.access_token,
        }


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        # If successful, add user details to response
        if response.status_code == 200:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            user = serializer.user
            from .serializers import UserDetailSerializer
            user_serializer = UserDetailSerializer(user)
            
            # Modify response to include user details
            response.data = {
                'success': True,
                'message': 'Login successful',
                'data': {
                    'access_token': str(response.data['access']),
                    'refresh_token': str(response.data['refresh']),
                    'user': user_serializer.data
                }
            }
        
        return response