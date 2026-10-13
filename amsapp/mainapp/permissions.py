from rest_framework import status
from rest_framework.response import Response

from .models import RoleMenu


def is_superadmin(user):
    role = getattr(user, "role", None)
    role_name = getattr(role, "role_name", "")
    return role_name.lower().startswith("superadmin")


def has_menu_permission(user, menu_link, permission):
    """Check a user's RoleMenu permission, with superadmin as a full-access bypass."""
    if is_superadmin(user):
        return True

    role = getattr(user, "role", None)
    if not role:
        return False

    role_menu = RoleMenu.objects.filter(role=role, menu__link=menu_link).first()
    if not role_menu:
        return False

    permissions = role_menu.permissions or {}
    return bool(permissions.get(permission))


def require_menu_permission(request, menu_link, permission, message):
    if has_menu_permission(request.user, menu_link, permission):
        return None

    return Response(
        {
            "success": False,
            "message": message,
        },
        status=status.HTTP_403_FORBIDDEN,
    )
