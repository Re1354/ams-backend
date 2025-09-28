from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.utils import extend_schema, OpenApiExample
from ..serializers import LoginSerializer, UserDetailSerializer
from ..models import User


@extend_schema(
    tags=['Authentication'],
    summary='User Login',
    description='Authenticate user and return simple token with user details',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'username': {
                    'type': 'string',
                    'description': 'Username for login',
                    'example': 'admin'
                },
                'password': {
                    'type': 'string',
                    'description': 'Password for login',
                    'example': 'admin123'
                }
            },
            'required': ['username', 'password']
        }
    },
    responses={
        200: {
            'description': 'Login successful',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Login successful',
                        'data': {
                            'token': 'abc123def456ghi789...',
                            'user': {
                                'id': 1,
                                'username': 'admin',
                                'email': 'admin@example.com',
                                'created_at': '2024-01-01T10:00:00Z',
                                'role_details': {
                                    'id': 1,
                                    'role_name': 'superadmin'
                                }
                            }
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Invalid credentials or validation error',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Invalid credentials',
                        'errors': ['Invalid credentials']
                    }
                }
            }
        }
    },
    examples=[
        OpenApiExample(
            'Login Request',
            summary='Example login request',
            description='Login with username and password',
            value={
                'username': 'admin',
                'password': 'admin123'
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Authenticate user and return JWT tokens with user details
    """
    serializer = LoginSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.validated_data['user']
        
        # Create a mock Django user object for JWT token generation
        class MockUser:
            def __init__(self, pk, username):
                self.pk = pk
                self.id = pk
                self.username = username
                self.is_authenticated = True
                self.is_active = True
        
        mock_user = MockUser(user.id, user.username)
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(mock_user)
        access_token = refresh.access_token
        
        # Get user details
        user_serializer = UserDetailSerializer(user)
        
        return Response({
            'success': True,
            'message': 'Login successful',
            'data': {
                'access_token': str(access_token),
                'refresh_token': str(refresh),
                'user': user_serializer.data
            }
        }, status=status.HTTP_200_OK)
    
    return Response({
        'success': False,
        'message': 'Invalid credentials',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentication'],
    summary='Verify Token',
    description='Verify token and return user details',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'token': {
                    'type': 'string',
                    'description': 'Authentication token',
                    'example': 'abc123def456ghi789...'
                }
            },
            'required': ['token']
        }
    },
    responses={
        200: {
            'description': 'Token is valid',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Token is valid',
                        'data': {
                            'user': {
                                'id': 1,
                                'username': 'admin',
                                'email': 'admin@example.com',
                                'created_at': '2024-01-01T10:00:00Z',
                                'role_details': {
                                    'id': 1,
                                    'role_name': 'superadmin'
                                }
                            }
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Invalid token',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Invalid token',
                        'errors': ['Token is invalid or expired']
                    }
                }
            }
        }
    },
    examples=[
        OpenApiExample(
            'Verify Token Request',
            summary='Example token verification request',
            description='Verify authentication token',
            value={
                'token': 'abc123def456ghi789...'
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_token_view(request):
    """
    Verify JWT token and return user details
    """
    token = request.data.get('token')
    
    if not token:
        return Response({
            'success': False,
            'message': 'Token is required',
            'errors': ['token field is required']
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        import jwt
        from django.conf import settings
        
        # Validate token
        UntypedToken(token)
        
        # Decode token to get user_id
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        user_id = decoded.get('user_id')
        
        if user_id:
            user = User.objects.get(id=user_id)
            user_serializer = UserDetailSerializer(user)
            
            return Response({
                'success': True,
                'message': 'Token is valid',
                'data': {
                    'user': user_serializer.data
                }
            }, status=status.HTTP_200_OK)
        else:
            raise ValueError("No user_id in token")
            
    except (InvalidToken, TokenError, User.DoesNotExist, jwt.ExpiredSignatureError, ValueError):
        return Response({
            'success': False,
            'message': 'Invalid token',
            'errors': ['Token is invalid or expired']
        }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Authentication'],
    summary='Refresh Token',
    description='Refresh access token using refresh token',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'refresh': {
                    'type': 'string',
                    'description': 'Refresh token',
                    'example': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'
                }
            },
            'required': ['refresh']
        }
    },
    responses={
        200: {
            'description': 'Token refreshed successfully',
            'content': {
                'application/json': {
                    'example': {
                        'access': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'
                    }
                }
            }
        },
        400: {
            'description': 'Invalid refresh token',
            'content': {
                'application/json': {
                    'example': {
                        'detail': 'Token is blacklisted',
                        'code': 'token_not_valid'
                    }
                }
            }
        }
    },
    examples=[
        OpenApiExample(
            'Refresh Token Request',
            summary='Example refresh token request',
            description='Refresh access token using refresh token',
            value={
                'refresh': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...'
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """
    Refresh access token using refresh token
    """
    view = TokenRefreshView.as_view()
    return view(request)