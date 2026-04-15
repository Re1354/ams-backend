from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction

from mainapp.models import Role, User


class Command(BaseCommand):
    help = 'Seed the default superadmin user account'

    def handle(self, *args, **options):
        with transaction.atomic():
            superadmin_role, _ = Role.objects.get_or_create(role_name='superadmin')

            defaults = {
                'email': 'admin@example.com',
                'password': make_password('admin123'),
                'role': superadmin_role,
            }

            admin_user, created = User.objects.get_or_create(
                username='admin',
                defaults=defaults,
            )

            if not created:
                updated_fields = []
                if admin_user.email != defaults['email']:
                    admin_user.email = defaults['email']
                    updated_fields.append('email')
                if admin_user.role_id != superadmin_role.id:
                    admin_user.role = superadmin_role
                    updated_fields.append('role')
                if updated_fields:
                    admin_user.save(update_fields=updated_fields)

            if created:
                self.stdout.write(self.style.SUCCESS('Created admin user and ensured superadmin role exists'))
            else:
                self.stdout.write(self.style.SUCCESS('Admin user already exists and was verified'))
