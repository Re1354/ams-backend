"""Add the "Proctoring" menu row (Menu Management cannot set a menu's component).

Same pattern as mainapp 0063 (Report Signatories): superadmin gets full access;
other roles get access through Menu Access Management.

Deploy note: apply this together with the new admin portal. Applied alone, the
old admin portal would show the menu with a "page not found" screen.
"""
from django.db import migrations

LINK = "/proctoring"
COMPONENT = "ProctoringDashboard"
FULL_ACCESS = {"read": True, "write": True, "edit": True, "delete": True}


def add_proctoring_menu(apps, schema_editor):
    Menu = apps.get_model("mainapp", "Menu")
    Role = apps.get_model("mainapp", "Role")
    RoleMenu = apps.get_model("mainapp", "RoleMenu")

    menu = Menu.objects.filter(link=LINK).first()
    if menu is None:
        menu = Menu.objects.create(label="Proctoring", icon="Eye", link=LINK, component=COMPONENT)
    elif menu.component != COMPONENT:
        menu.component = COMPONENT
        menu.save(update_fields=["component"])

    superadmin = Role.objects.filter(role_name__iexact="superadmin").first()
    if superadmin:
        RoleMenu.objects.update_or_create(role=superadmin, menu=menu, defaults={"permissions": FULL_ACCESS})


def remove_proctoring_menu(apps, schema_editor):
    Menu = apps.get_model("mainapp", "Menu")
    Menu.objects.filter(link=LINK, component=COMPONENT).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("proctoring", "0001_initial"),
        ("mainapp", "0065_backfill_profile_and_acceptance_data"),
    ]

    operations = [
        migrations.RunPython(add_proctoring_menu, remove_proctoring_menu),
    ]
