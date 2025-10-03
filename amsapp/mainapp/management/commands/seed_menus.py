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
                    'link': '/dashboard',
                    'component': 'Dashboard'
                },
                {
                    'label': 'Create Questions',
                    'icon': 'Plus',
                    'link': '/create-questions',
                    'component': 'CreateQuestions'
                },
                {
                    'label': 'All Questions',
                    'icon': 'FileText',
                    'link': '/all-questions',
                    'component': 'AllQuestions'
                },
                {
                    'label': 'Students',
                    'icon': 'Users',
                    'link': '/students',
                    'component': 'Students'
                },
                {
                    'label': 'Exam Schedule',
                    'icon': 'Calendar',
                    'link': '/exam-schedule',
                    'component': 'ExamSchedule'
                },
                {
                    'label': 'Users Management',
                    'icon': 'UserCheck',
                    'link': '/users-management',
                    'component': 'UsersManagement'
                },
                {
                    'label': 'Role Management',
                    'icon': 'Shield',
                    'link': '/role-management',
                    'component': 'RoleManagement'
                },
                {
                    'label': 'Menu Management',
                    'icon': 'Menu',
                    'link': '/menu-management',
                    'component': 'MenuManagement'
                },
                {
                    'label': 'Menu Access Management',
                    'icon': 'Key',
                    'link': '/menu-access-management',
                    'component': 'MenuAccessManagement'
                },
                {
                    'label': 'Department Management',
                    'icon': 'Building',
                    'link': '/department-management',
                    'component': 'DepartmentManagement'
                },
                {
                    'label': 'Subject Management',
                    'icon': 'BookOpen',
                    'link': '/subject-management',
                    'component': 'SubjectManagement'
                },
                {
                    'label': 'Subject Department Mapping',
                    'icon': 'Layers',
                    'link': '/subject-department-mapping',
                    'component': 'SubjectDepartmentMapping'
                },
                {
                    'label':'Student Assign',
                    'icon':'UserPlus',
                    'link':'/student-assign-teacher-exam',
                    'component':'StudentAssignTeacherExam'
                },
                {
                    'label': 'Results',
                    'icon': 'FilePlus',
                    'link': '/results',
                    'component': 'Results'
                },
                {
                    'label': 'Blocked Questions',
                    'icon': 'Slash',
                    'link': '/blocked-questions',
                    'component': 'BlockedQuestions'
                },
                {
                    'label': 'Published Exams',
                    'icon': 'FileCheck',
                    'link': '/published-exams',
                    'component': 'PublishedExams'
                }
               
            ]

            # Create or get menus
            created_menus = []
            for menu_item in menu_data:
                menu, created = Menu.objects.get_or_create(
                    label=menu_item['label'],
                    defaults={
                        'icon': menu_item['icon'],
                        'link': menu_item['link'],
                        'component': menu_item['component']
                    }
                )
                # Update existing menu if component, icon, or link changed
                updated = False
                if not created:
                    if menu.icon != menu_item['icon']:
                        menu.icon = menu_item['icon']
                        updated = True
                    if menu.link != menu_item['link']:
                        menu.link = menu_item['link']
                        updated = True
                    if menu.component != menu_item['component']:
                        menu.component = menu_item['component']
                        updated = True
                    if updated:
                        menu.save()
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
