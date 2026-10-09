from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from ..serializers import UserSerializer, UserDetailSerializer
from ..models import User
from ..authentication import CustomJWTAuthentication


@extend_schema(
    operation_id='get_all_users',
    tags=['Users'],
    summary='Get All Users',
    description='Retrieve users with role-based filtering: superadmin sees all users, other users only see users from their department',
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
@authentication_classes([CustomJWTAuthentication])
def get_all_users(request):
    """
    Retrieve users with role-based filtering:
    - Global: All users
    - Others: Only users from their department(s)
    """
    user = request.user
    custom_user = user.custom_user if hasattr(user, 'custom_user') else None
    
    from ..services.access_control import get_user_access_scope
    scope = get_user_access_scope(custom_user)
    
    if scope['is_global']:
        users = User.objects.all().select_related('role', 'department', 'faculty').order_by('id')
    else:
        if scope['department_ids']:
            users = User.objects.filter(
                department_id__in=scope['department_ids']
            ).select_related('role', 'department', 'faculty').order_by('id')
        else:
            users = User.objects.none()
    
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
@authentication_classes([CustomJWTAuthentication])
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
    operation_id='get_user_by_id',
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
@authentication_classes([CustomJWTAuthentication])
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
@authentication_classes([CustomJWTAuthentication])
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
@authentication_classes([CustomJWTAuthentication])
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


@extend_schema(
    operation_id='get_all_teachers',
    tags=['Users'],
    summary='Get All Teachers',
    description='Retrieve teachers with role-based filtering: superadmin sees all teachers, other users only see teachers from their department',
    responses={
        200: {
            'description': 'Teachers retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Teachers retrieved successfully',
                        'data': [
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
        }
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([CustomJWTAuthentication])
def get_all_teachers(request):
    """
    Retrieve teachers with role-based filtering:
    - superadmin: All teachers
    - Other users: Only teachers from their department
    """
    user = request.user
    
    # Get the custom user and role information
    if hasattr(user, 'custom_user'):
        custom_user = user.custom_user
        
        # Check if user has a role
        if custom_user.role:
            role_name = custom_user.role.role_name.lower()
            
            # Check if superadmin - return all teachers
            if role_name == 'superadmin':
                teachers = User.objects.filter(
                    role__role_name__icontains='teacher'
                ).select_related('role', 'department').order_by('id')
            else:
                # For non-superadmin users, filter by department
                if custom_user.department:
                    user_dept_shortname = custom_user.department.department_shortname
                    teachers = User.objects.filter(
                        role__role_name__icontains='teacher',
                        department__department_shortname=user_dept_shortname
                    ).select_related('role', 'department').order_by('id')
                else:
                    # If user has no department assigned, return empty queryset
                    teachers = User.objects.none()
        else:
            # If user has no role, return empty queryset
            teachers = User.objects.none()
    else:
        # If no custom_user, return empty queryset for security
        teachers = User.objects.none()
    
    serializer = UserDetailSerializer(teachers, many=True)
    
    return Response({
        'success': True,
        'message': 'Teachers retrieved successfully',
        'data': serializer.data
    }, status=status.HTTP_200_OK)