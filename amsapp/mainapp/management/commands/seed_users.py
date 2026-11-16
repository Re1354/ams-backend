from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction

from mainapp.models import Role, User


class Command(BaseCommand):
    help = 'Seed the default superadmin user account'

    def handle(self, *args, **options):
        with transaction.atomic():
            superadmin_role, _ = Role.objects.get_or_create(role_name='superadmin')

            # Ensure Super-Admin user 'admin' with password 'admin123' exists
            admin_user, created = User.objects.get_or_create(
                username='admin',
                defaults={
                    'email': 'admin@diu.edu.bd',
                    'password': make_password('admin123'),
                    'role': superadmin_role,
                },
            )

            if not created:
                admin_user.password = make_password('admin123')
                admin_user.role = superadmin_role
                admin_user.save(update_fields=['password', 'role'])

            self.stdout.write(self.style.SUCCESS("Super-Admin credentials verified: admin / admin123"))
