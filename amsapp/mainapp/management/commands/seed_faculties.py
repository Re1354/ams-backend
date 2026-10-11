from django.core.management.base import BaseCommand
from django.db import transaction
from mainapp.models import Faculty, FacultyDepartment


class Command(BaseCommand):
    help = 'Seed faculties and their department mappings'

    def handle(self, *args, **options):
        with transaction.atomic():
            faculties_data = [
                {'id': 1, 'name': 'Faculty of Science and Information Technology', 'short': 'FSIT', 'dept_ids': [9, 10, 11, 12, 13, 14, 16]},
                {'id': 3, 'name': 'Faculty of Engineering', 'short': 'FE', 'dept_ids': [17, 18, 19, 20]},
                {'id': 4, 'name': 'Faculty of Business and Entrepreneurship', 'short': 'FBE', 'dept_ids': [1, 2, 3, 4, 5, 6, 7, 8]},
                {'id': 5, 'name': 'Faculty of Humanities and Social Science', 'short': 'FHSS', 'dept_ids': [15, 26, 27, 28, 29, 30]},
                {'id': 6, 'name': 'Faculty of Allied Health Sciences', 'short': 'FAHS', 'dept_ids': [21, 22, 23, 24, 25]},
            ]

            for item in faculties_data:
                faculty, created = Faculty.objects.update_or_create(
                    id=item['id'],
                    defaults={
                        'faculty_name': item['name'],
                        'faculty_shortname': item['short'],
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created faculty: {faculty.faculty_name} ({faculty.faculty_shortname})"))
                else:
                    self.stdout.write(self.style.WARNING(f"Updated faculty: {faculty.faculty_name} ({faculty.faculty_shortname})"))

                mapping, m_created = FacultyDepartment.objects.update_or_create(
                    faculty=faculty,
                    defaults={
                        'department_ids': item['dept_ids']
                    }
                )
                if m_created:
                    self.stdout.write(self.style.SUCCESS(f"Mapped {len(item['dept_ids'])} departments to {faculty.faculty_shortname}"))
                else:
                    self.stdout.write(self.style.WARNING(f"Updated department mapping for {faculty.faculty_shortname}"))

            self.stdout.write(self.style.SUCCESS("\nFaculties and departments seeded successfully!"))
