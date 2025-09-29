from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from ..models import Menu, RoleMenu, Role
from ..serializers import MenuSerializer, RoleMenuSerializer
from ..authentication import CustomJWTAuthentication


@extend_schema(
    tags=['Menus'],
    summary="Get all menus",
    description="Retrieve all available menus in the system.",
    responses={
        200: OpenApiResponse(
            response=MenuSerializer(many=True),
            description="List of all menus"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def all_menus(request):
    """Get all menus"""
    menus = Menu.objects.all().order_by('id')
    serializer = MenuSerializer(menus, many=True)
    return Response({
        'success': True,
        'data': serializer.data,
        'message': 'Menus retrieved successfully'
    })


@extend_schema(
    tags=['Menus'],
    summary="Get menus for a specific role",
    description="Retrieve all menus assigned to a specific role with permissions.",
    parameters=[
        OpenApiParameter(
            name='role_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description='Role ID to get menus for'
        )
    ],
    responses={
        200: OpenApiResponse(
            response=RoleMenuSerializer(many=True),
            description="List of menus for the role"
        ),
        404: OpenApiResponse(description="Role not found")
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def role_menus(request, role_id):
    """Get menus for a specific role"""
    role = get_object_or_404(Role, id=role_id)
    role_menus = RoleMenu.objects.filter(role=role).select_related('menu').order_by('menu__id')
    serializer = RoleMenuSerializer(role_menus, many=True)
    
    return Response({
        'success': True,
        'data': serializer.data,
        'role': role.role_name,
        'message': f'Menus for {role.role_name} retrieved successfully'
    })


@extend_schema(
    tags=['Role-Menu Management'],
    summary="Assign menus to role",
    description="Assign multiple menus to a role with specific permissions. Only superadmin can perform this action.",
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'role_id': {'type': 'integer', 'description': 'Role ID'},
                'menus': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'menu_id': {'type': 'integer'},
                            'permissions': {
                                'type': 'object',
                                'properties': {
                                    'read': {'type': 'boolean'},
                                    'write': {'type': 'boolean'},
                                    'edit': {'type': 'boolean'},
                                    'delete': {'type': 'boolean'}
                                }
                            }
                        }
                    }
                }
            },
            'example': {
                'role_id': 2,
                'menus': [
                    {
                        'menu_id': 1,
                        'permissions': {
                            'read': True,
                            'write': False,
                            'edit': False,
                            'delete': False
                        }
                    },
                    {
                        'menu_id': 2,
                        'permissions': {
                            'read': True,
                            'write': True,
                            'edit': True,
                            'delete': False
                        }
                    }
                ]
            }
        }
    },
    responses={
        200: OpenApiResponse(description="Menus assigned successfully"),
        400: OpenApiResponse(description="Invalid data"),
        403: OpenApiResponse(description="Only superadmin can assign menus"),
        404: OpenApiResponse(description="Role or Menu not found")
    }
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_menus_to_role(request):
    """Assign menus to a role with permissions (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can assign menus to roles'
        }, status=status.HTTP_403_FORBIDDEN)
    
    role_id = request.data.get('role_id')
    menus_data = request.data.get('menus', [])
    
    if not role_id or not menus_data:
        return Response({
            'success': False,
            'message': 'role_id and menus are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get role
    role = get_object_or_404(Role, id=role_id)
    
    assigned_menus = []
    updated_menus = []
    
    for menu_data in menus_data:
        menu_id = menu_data.get('menu_id')
        permissions = menu_data.get('permissions', {})
        
        if not menu_id:
            continue
            
        menu = get_object_or_404(Menu, id=menu_id)
        
        # Create or update role-menu assignment
        role_menu, created = RoleMenu.objects.update_or_create(
            role=role,
            menu=menu,
            defaults={'permissions': permissions}
        )
        
        if created:
            assigned_menus.append(menu.label)
        else:
            updated_menus.append(menu.label)
    
    return Response({
        'success': True,
        'message': f'Menus assigned/updated for role: {role.role_name}',
        'assigned': assigned_menus,
        'updated': updated_menus
    })


@extend_schema(
    tags=['Role-Menu Management'],
    summary="Remove menu from role",
    description="Remove a menu assignment from a role. Only superadmin can perform this action.",
    parameters=[
        OpenApiParameter(
            name='role_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH
        ),
        OpenApiParameter(
            name='menu_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: OpenApiResponse(description="Menu removed from role successfully"),
        403: OpenApiResponse(description="Only superadmin can remove menus"),
        404: OpenApiResponse(description="Role-Menu assignment not found")
    }
)
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_menu_from_role(request, role_id, menu_id):
    """Remove menu from role (only superadmin)"""
    
    # Check if user is superadmin
    user = request.user
    if not user.role or user.role.role_name != 'superadmin':
        return Response({
            'success': False,
            'message': 'Only superadmin can remove menus from roles'
        }, status=status.HTTP_403_FORBIDDEN)
    
    role_menu = get_object_or_404(
        RoleMenu, 
        role_id=role_id, 
        menu_id=menu_id
    )
    
    menu_label = role_menu.menu.label
    role_name = role_menu.role.role_name
    
    role_menu.delete()
    
    return Response({
        'success': True,
        'message': f'Menu "{menu_label}" removed from role "{role_name}"'
    })


@extend_schema(
    tags=['User Menus'],
    summary="Get current user's menus",
    description="Get all menus accessible to the current authenticated user based on their role.",
    responses={
        200: OpenApiResponse(
            description="User's accessible menus with permissions"
        )
    }
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_menus(request):
    """Get current user's accessible menus based on their role"""
    user = request.user
    
    if not user.role:
        return Response({
            'success': False,
            'message': 'User has no role assigned'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Get user's role menus
    role_menus = RoleMenu.objects.filter(
        role=user.role
    ).select_related('menu').order_by('menu__id')
    
    menus_data = []
    for role_menu in role_menus:
        menus_data.append({
            'id': role_menu.menu.id,
            'title': role_menu.menu.label,
            'icon': role_menu.menu.icon,
            'link': role_menu.menu.link,
            'permissions': role_menu.permissions
        })
    
    return Response({
        'success': True,
        'data': menus_data,
        'role': user.role.role_name,
        'message': f'Menus for user {user.username} retrieved successfully'
    })