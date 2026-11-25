"""The Proctoring menu row comes from a data migration (Menu Management cannot set a component)."""
import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from mainapp.models import Menu, Role, RoleMenu

menu_migration = importlib.import_module("proctoring.migrations.0002_proctoring_menu")

FULL = {"read": True, "write": True, "edit": True, "delete": True}


class ProctoringMenuMigrationTests(TestCase):
    def test_menu_row_exists_after_migrations(self):
        menu = Menu.objects.get(link="/proctoring")
        self.assertEqual(
            (menu.label, menu.component, menu.icon), ("Proctoring", "ProctoringDashboard", "Eye")
        )

    def test_add_menu_grants_superadmin_only_and_is_idempotent(self):
        Menu.objects.filter(link="/proctoring").delete()
        superadmin, _ = Role.objects.get_or_create(role_name="superadmin")
        teacher, _ = Role.objects.get_or_create(role_name="teacher")

        menu_migration.add_proctoring_menu(django_apps, None)
        menu_migration.add_proctoring_menu(django_apps, None)

        self.assertEqual(Menu.objects.filter(link="/proctoring").count(), 1)
        self.assertEqual(RoleMenu.objects.get(role=superadmin, menu__link="/proctoring").permissions, FULL)
        self.assertFalse(RoleMenu.objects.filter(role=teacher, menu__link="/proctoring").exists())

    def test_add_menu_keeps_existing_row_and_its_label(self):
        Menu.objects.filter(link="/proctoring").update(label="Exam Proctoring", icon="Shield")
        menu_migration.add_proctoring_menu(django_apps, None)
        menu = Menu.objects.get(link="/proctoring")
        self.assertEqual((menu.label, menu.icon, menu.component), ("Exam Proctoring", "Shield", "ProctoringDashboard"))

    def test_remove_menu_deletes_row_and_grants(self):
        superadmin, _ = Role.objects.get_or_create(role_name="superadmin")
        menu_migration.add_proctoring_menu(django_apps, None)
        menu_migration.remove_proctoring_menu(django_apps, None)
        self.assertFalse(Menu.objects.filter(link="/proctoring").exists())
        self.assertFalse(RoleMenu.objects.filter(role=superadmin, menu__link="/proctoring").exists())
