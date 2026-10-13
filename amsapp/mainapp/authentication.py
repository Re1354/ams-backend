from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from .models import User


class CustomUser:
    """
    Wrapper to make our custom User model compatible with Django's authentication system
    """
    def __init__(self, custom_user):
        self.custom_user = custom_user
        self.pk = custom_user.pk
        self.id = custom_user.id
        self.username = custom_user.username
        self.email = custom_user.email
        self.role = custom_user.role  # Add role attribute
        self.created_at = custom_user.created_at
        self.access_type = getattr(custom_user, 'access_type', 'DEPARTMENT')
        self.is_global_access = getattr(custom_user, 'is_global_access', False)
        self.faculty = getattr(custom_user, 'faculty', None)
        self.faculty_id = getattr(custom_user, 'faculty_id', None)
        self.department = getattr(custom_user, 'department', None)
        self.department_id = getattr(custom_user, 'department_id', None)
        self.is_active = True
        self.is_authenticated = True
        self.is_anonymous = False
    
    def __getattr__(self, item):
        return getattr(self.custom_user, item)

    def __str__(self):
        return self.username


class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that works with our User model instead of Django's built-in User model.
    """
    
    def get_user(self, validated_token):
        """
        Attempts to find and return a user using the given validated token.
        """
        try:
            user_id = validated_token['user_id']
        except KeyError:
            raise InvalidToken('Token contained no recognizable user identification')

        try:
            custom_user = User.objects.get(id=user_id)
            # Return our custom user wrapped for Django compatibility
            return CustomUser(custom_user)
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found')