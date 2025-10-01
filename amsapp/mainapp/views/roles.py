from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiExample
from drf_spectacular.openapi import OpenApiParameter
from ..serializers import RoleSerializer
from ..models import Role


@extend_schema(
    operation_id='get_all_roles',
    tags=['Roles'],
    summary='Get All Roles',
    description='Retrieve all roles in the system',
    responses={
        200: {
            'description': 'Roles retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Roles retrieved successfully',
                        'data': [
                            {
                                'id': 1,
                                'role_name': 'Admin'
                            },
                            {
                                'id': 2,
                                'role_name': 'Teacher'
                            },
                            {
                                'id': 3,
                                'role_name': 'Student'
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
def get_all_roles(request):
    """
    Retrieve all roles in the system
    """
    roles = Role.objects.all().order_by('id')
    serializer = RoleSerializer(roles, many=True)
    
    return Response({
        'success': True,
        'message': 'Roles retrieved successfully',
        'data': serializer.data
    }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['Roles'],
    summary='Create New Role',
    description='Create a new role in the system',
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'role_name': {
                    'type': 'string',
                    'description': 'Name of the role',
                    'example': 'Manager'
                }
            },
            'required': ['role_name']
        }
    },
    responses={
        201: {
            'description': 'Role created successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Role created successfully',
                        'data': {
                            'id': 4,
                            'role_name': 'Manager'
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
                            'role_name': ['Role name already exists']
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
            'Create Role Request',
            summary='Example role creation request',
            description='Create a new role with a unique name',
            value={
                'role_name': 'Manager'
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_role(request):
    """
    Create a new role in the system
    """
    serializer = RoleSerializer(data=request.data)
    
    if serializer.is_valid():
        role = serializer.save()
        return Response({
            'success': True,
            'message': 'Role created successfully',
            'data': serializer.data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'success': False,
        'message': 'Validation error',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    operation_id='get_role_by_id',
    tags=['Roles'],
    summary='Get Role by ID',
    description='Retrieve a specific role by its ID',
    parameters=[
        OpenApiParameter(
            name='role_id',
            description='ID of the role to retrieve',
            required=True,
            type=int,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: {
            'description': 'Role retrieved successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Role retrieved successfully',
                        'data': {
                            'id': 1,
                            'role_name': 'Admin'
                        }
                    }
                }
            }
        },
        404: {
            'description': 'Role not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Role not found',
                        'errors': ['Role with ID 999 does not exist']
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
def get_role_by_id(request, role_id):
    """
    Retrieve a specific role by its ID
    """
    try:
        role = Role.objects.get(id=role_id)
        serializer = RoleSerializer(role)
        
        return Response({
            'success': True,
            'message': 'Role retrieved successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Role.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Role not found',
            'errors': [f'Role with ID {role_id} does not exist']
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=['Roles'],
    summary='Update Role',
    description='Update an existing role',
    parameters=[
        OpenApiParameter(
            name='role_id',
            description='ID of the role to update',
            required=True,
            type=int,
            location=OpenApiParameter.PATH
        )
    ],
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'role_name': {
                    'type': 'string',
                    'description': 'Updated name of the role',
                    'example': 'Senior Manager'
                }
            },
            'required': ['role_name']
        }
    },
    responses={
        200: {
            'description': 'Role updated successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Role updated successfully',
                        'data': {
                            'id': 4,
                            'role_name': 'Senior Manager'
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
                            'role_name': ['Role name already exists']
                        }
                    }
                }
            }
        },
        404: {
            'description': 'Role not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Role not found',
                        'errors': ['Role with ID 999 does not exist']
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
            'Update Role Request',
            summary='Example role update request',
            description='Update an existing role with a new name',
            value={
                'role_name': 'Senior Manager'
            },
            request_only=True,
            media_type='application/json'
        )
    ]
)
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_role(request, role_id):
    """
    Update an existing role
    """
    try:
        role = Role.objects.get(id=role_id)
        serializer = RoleSerializer(role, data=request.data)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Role updated successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Validation error',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    except Role.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Role not found',
            'errors': [f'Role with ID {role_id} does not exist']
        }, status=status.HTTP_404_NOT_FOUND)


@extend_schema(
    tags=['Roles'],
    summary='Delete Role',
    description='Delete an existing role',
    parameters=[
        OpenApiParameter(
            name='role_id',
            description='ID of the role to delete',
            required=True,
            type=int,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: {
            'description': 'Role deleted successfully',
            'content': {
                'application/json': {
                    'example': {
                        'success': True,
                        'message': 'Role deleted successfully'
                    }
                }
            }
        },
        400: {
            'description': 'Cannot delete role with associated users',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Cannot delete role',
                        'errors': ['Cannot delete role. There are 3 users associated with this role.']
                    }
                }
            }
        },
        404: {
            'description': 'Role not found',
            'content': {
                'application/json': {
                    'example': {
                        'success': False,
                        'message': 'Role not found',
                        'errors': ['Role with ID 999 does not exist']
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
def delete_role(request, role_id):
    """
    Delete an existing role
    """
    try:
        role = Role.objects.get(id=role_id)
        
        # Check if there are users associated with this role
        user_count = role.users.count()
        if user_count > 0:
            return Response({
                'success': False,
                'message': 'Cannot delete role',
                'errors': [f'Cannot delete role. There are {user_count} users associated with this role.']
            }, status=status.HTTP_400_BAD_REQUEST)
        
        role.delete()
        
        return Response({
            'success': True,
            'message': 'Role deleted successfully'
        }, status=status.HTTP_200_OK)
    
    except Role.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Role not found',
            'errors': [f'Role with ID {role_id} does not exist']
        }, status=status.HTTP_404_NOT_FOUND)