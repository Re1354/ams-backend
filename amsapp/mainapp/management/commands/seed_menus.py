from django.core.management.base import BaseCommand
from mainapp.models import Menu, Role, RoleMenu
from django.db import transaction


class Command(BaseCommand):
    help = 'Seed menu data and create superadmin role with full permissions'

    def handle(self, *args, **options):
        with transaction.atomic():
            # Menu data based on your frontend structure
            menu_data = [
                {
                    'label': 'Dashboard',
                    'icon': 'LayoutDashboard',
                    'link': '/dashboard'
                },
                {
                    'label': 'Create Questions',
                    'icon': 'Plus',
                    'link': '/create-questions'
                },
                {
                    'label': 'All Questions',
                    'icon': 'FileText',
                    'link': '/all-questions'
                },
                {
                    'label': 'Students',
                    'icon': 'Users',
                    'link': '/students'
                },
                {
                    'label': 'Exam Schedule',
                    'icon': 'Calendar',
                    'link': '/exam-schedule'
                },
                {
                    'label': 'Users Management',
                    'icon': 'UserCheck',
                    'link': '/users-management'
                },
                {
                    'label': 'Role Management',
                    'icon': 'Shield',
                    'link': '/role-management'
                },
                {
                    'label': 'Menu Management',
                    'icon': 'Menu',
                    'link': '/menu-management'
                },
                {
                    'label': 'Menu Access Management',
                    'icon': 'Key',
                    'link': '/menu-access-management'
                },
                {
                    'label': 'Department Management',
                    'icon': 'Building',
                    'link': '/department-management'
                },
                {
                    'label': 'Subject Management',
                    'icon': 'BookOpen',
                    'link': '/subject-management'
                },
                {
                    'label': 'Subject Department Mapping',
                    'icon': 'Layers',
                    'link': '/subject-department-mapping'
                }
               
            ]

            # Create or get menus
            created_menus = []
            for menu_item in menu_data:
                menu, created = Menu.objects.get_or_create(
                    label=menu_item['label'],
                    defaults={
                        'icon': menu_item['icon'],
                        'link': menu_item['link']
                    }
                )
                created_menus.append(menu)
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f'Created menu: {menu.label}')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f'Menu already exists: {menu.label}')
                    )

            # Create or get superadmin role
            superadmin_role, created = Role.objects.get_or_create(
                role_name='superadmin'
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS('Created superadmin role')
                )
            else:
                self.stdout.write(
                    self.style.WARNING('Superadmin role already exists')
                )

            # Assign all menus to superadmin with full permissions
            full_permissions = {
                "read": True,
                "write": True,
                "edit": True,
                "delete": True
            }

            for menu in created_menus:
                role_menu, created = RoleMenu.objects.get_or_create(
                    role=superadmin_role,
                    menu=menu,
                    defaults={'permissions': full_permissions}
                )
                if created:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Assigned {menu.label} to superadmin with full permissions'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Menu {menu.label} already assigned to superadmin'
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS('\nSeeding completed successfully!')
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created {len(created_menus)} menus and assigned to superadmin role'
                )
            )
