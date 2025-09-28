from rest_framework_simplejwt.tokens import RefreshToken
from .models import User


class CustomRefreshToken(RefreshToken):
    """
    Custom refresh token for our User model
    """
    
    @classmethod
    def for_user(cls, user):
        """
        Returns an authorization grant token object for the given user that
        will be provided after authenticating the user's credentials.
        """
        user_id = getattr(user, 'id', None)
        if not user_id:
            raise ValueError('Cannot create token: User instance must have a primary key value')
        
        token = cls()
        token['user_id'] = user_id
        
        return token