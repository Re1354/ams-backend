from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from ..serializers import UserSerializer, UserDetailSerializer
from ..models import User


@extend_schema(
    tags=['Users'],
    summary='Get All Users',
    description='Retrieve all users in the system with their role information',
    responses={
        200: {
            'description': 'Users retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Users retrieved successfully',
                        'data': [
                            {
                                'id': 1,
                                'username': 'admin',
                                'email': 'admin@example.com',
                                'created_at': '2024-01-01T10:00:00Z',
                                'role_details': {
                                    'id': 1,
                                    'role_name': 'Admin'
                                },
                                'department_details': {
                                    'id': 1,
                                    'department_name': 'IT Department'
                                }
                            },
                            {
                                'id': 2,
                                'username': 'teacher1',
                                'email': 'teacher1@example.com',
                                'created_at': '2024-01-02T10:00:00Z',
                                'role_details': {
                                    'id': 2,
                                    'role_name': 'Teacher'
                                },
                                'department_details': {
                                    'id': 2,
                                    'department_name': 'Computer Science'
                                }
                            }
                        ]
                    }
                }
            }
        },
        401: {
            'description': 'Authentication required',
            'content': {
                'application/json': {
                    'example': {
                        'detail': 'Authentication credentials were not provided.'
                    }
                }
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_all_users(request):
    """
    Retrieve all users in the system with their role information
    """
    users = User.objects.all().select_related('role').order_by('id')
    serializer = UserDetailSerializer(users, many=True)
    
    return Response({
        'success': True,
        'message': 'Users retrieved successfully',
        'data': serializer.data
    }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Users'],
    summary='Create New User',
    description='Create a new user in the system with optional role assignment',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'username': {
                    'type': 'string',
                    'description': 'Unique username for the user',
                    'example': 'newuser'
                },
                'email': {
                    'type': 'string',
                    'format': 'email',
                    'description': 'Unique email address for the user',
                    'example': 'newuser@example.com'
                },
                'password': {
                    'type': 'string',
                    'description': 'Password for the user (will be hashed)',
                    'example': 'securepassword123'
                },
                'role_id': {
                    'type': 'integer',
                    'description': 'ID of the role to assign to the user (optional)',
                    'example': 2,
                    'nullable': True
                },
                'department_id': {
                    'type': 'integer',
                    'description': 'ID of the department to assign to the user (optional)',
                    'example': 1,
                    'nullable': True
                }
            },
            'required': ['username', 'email', 'password']
        }
    },
    responses={
        201: {
            'description': 'User created successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'User created successfully',
                        'data': {
                            'id': 3,
                            'username': 'newuser',
                            'email': 'newuser@example.com',
                            'role_name': 'Teacher',
                            'department_name': 'Computer Science',
                            'created_at': '2024-01-03T10:00:00Z'
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Validation error',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Validation error',
                        'errors': {
                            'username': ['Username already exists'],
                            'email': ['Email already exists'],
                            'department_id': ['Department does not exist']
                        }
                    }
                }
            }
        },
        401: {
            'description': 'Authentication required',
            'content': {
                'application/json': {
                    'example': {
                        'detail': 'Authentication credentials were not provided.'
                    }
                }
            }
        }
    },
    examples=[
        OpenApiExample(
            'Create User Request',
            summary='Example user creation request',
            description='Create a new user with role and department assignment',
            value={
                'username': 'newuser',
                'email': 'newuser@example.com',
                'password': 'securepassword123',
                'role_id': 2,
                'department_id': 1
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_user(request):
    """
    Create a new user in the system with optional role and department assignment
    """
    serializer = UserSerializer(data=request.data)
    
    if serializer.is_valid():
        user = serializer.save()
        return Response({
            'success': True,
            'message': 'User created successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'success': False,
        'message': 'Validation error',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['Users'],
    summary='Get User by ID',
    description='Retrieve a specific user by their ID with role information',
    parameters=[
        OpenApiParameter(
            name='user_id',
            description='ID of the user to retrieve',
            required=True,
            type=int,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: {
            'description': 'User retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'User retrieved successfully',
                        'data': {
                            'id': 1,
                            'username': 'admin',
                            'email': 'admin@example.com',
                            'created_at': '2024-01-01T10:00:00Z',
                            'role_details': {
                                'id': 1,
                                'role_name': 'Admin'
                            },
                            'department_details': {
                                'id': 1,
                                'department_name': 'IT Department'
                            }
                        }
                    }
                }
            }
        },
        404: {
            'description': 'User not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'User not found',
                        'errors': ['User with ID 999 does not exist']
                    }
                }
            }
        },
        401: {
            'description': 'Authentication required',
            'content': {
                'application/json': {
                    'example': {
                        'detail': 'Authentication credentials were not provided.'
                    }
                }
            }
        }
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_by_id(request, user_id):
    """
    Retrieve a specific user by their ID with role information
    """
    try:
        user = User.objects.select_related('role').get(id=user_id)
        serializer = UserDetailSerializer(user)
        
        return Response({
            'success': True,
            'message': 'User retrieved successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'User not found',
            'errors': [f'User with ID {user_id} does not exist']
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=['Users'],
    summary='Update User',
    description='Update an existing user with optional role and password changes',
    parameters=[
        OpenApiParameter(
            name='user_id',
            description='ID of the user to update',
            required=True,
            type=int,
            location=OpenApiParameter.PATH
        )
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'username': {
                    'type': 'string',
                    'description': 'Updated username for the user',
                    'example': 'updateduser'
                },
                'email': {
                    'type': 'string',
                    'format': 'email',
                    'description': 'Updated email address for the user',
                    'example': 'updated@example.com'
                },
                'password': {
                    'type': 'string',
                    'description': 'New password for the user (optional, will be hashed)',
                    'example': 'newsecurepassword123'
                },
                'role_id': {
                    'type': 'integer',
                    'description': 'ID of the role to assign to the user (optional, use 0 to remove role)',
                    'example': 3,
                    'nullable': True
                }
            }
        }
    },
    responses={
        200: {
            'description': 'User updated successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'User updated successfully',
                        'data': {
                            'id': 3,
                            'username': 'updateduser',
                            'email': 'updated@example.com',
                            'role_name': 'Manager',
                            'created_at': '2024-01-03T10:00:00Z'
                        }
                    }
                }
            }
        },
        400: {
            'description': 'Validation error',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Validation error',
                        'errors': {
                            'username': ['Username already exists'],
                            'role_id': ['Role does not exist'],
                            'department_id': ['Department does not exist']
                        }
                    }
                }
            }
        },
        404: {
            'description': 'User not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'User not found',
                        'errors': ['User with ID 999 does not exist']
                    }
                }
            }
        },
        401: {
            'description': 'Authentication required',
            'content': {
                'application/json': {
                    'example': {
                        'detail': 'Authentication credentials were not provided.'
                    }
                }
            }
        }
    },
    examples=[
        OpenApiExample(
            'Update User Request',
            summary='Example user update request',
            description='Update an existing user with new role and department assignment',
            value={
                'username': 'updateduser',
                'email': 'updated@example.com',
                'role_id': 3,
                'department_id': 2
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    """
    Update an existing user with optional role, department and password changes
    """
    try:
        user = User.objects.get(id=user_id)
        serializer = UserSerializer(user, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'User updated successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'User not found',
            'errors': [f'User with ID {user_id} does not exist']
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=['Users'],
    summary='Delete User',
    description='Delete an existing user',
    parameters=[
        OpenApiParameter(
            name='user_id',
            description='ID of the user to delete',
            required=True,
            type=int,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: {
            'description': 'User deleted successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'User deleted successfully'
                    }
                }
            }
        },
        404: {
            'description': 'User not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'User not found',
                        'errors': ['User with ID 999 does not exist']
                    }
                }
            }
        },
        401: {
            'description': 'Authentication required',
            'content': {
                'application/json': {
                    'example': {
                        'detail': 'Authentication credentials were not provided.'
                    }
                }
            }
        }
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    """
    Delete an existing user
    """
    try:
        user = User.objects.get(id=user_id)
        user.delete()
        
        return Response({
            'success': True,
            'message': 'User deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'User not found',
            'errors': [f'User with ID {user_id} does not exist']
        }, status=status.HTTP_404_NOT_FOUND)