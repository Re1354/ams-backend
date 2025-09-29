from django.db import models
from .role import Role
from .menu import Menu


class RoleMenu(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_menus")
    menu = models.ForeignKey(Menu, on_delete=models.CASCADE, related_name="menu_roles")

    # Store permissions as JSON in PostgreSQL
    permissions = models.JSONField(
        default=dict,  # default is {}
        help_text='Example: {"read": true, "write": false, "edit": false, "delete": false}'
    )

    class Meta:
        db_table = "role_menus"
        unique_together = ("role", "menu")  # prevent duplicate role-menu mapping

    def __str__(self):
        return f"{self.role.role_name} -> {self.menu.label}"
