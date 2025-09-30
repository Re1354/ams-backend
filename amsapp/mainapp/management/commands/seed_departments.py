from django.core.management.base import BaseCommand
from mainapp.models import Department


class Command(BaseCommand):
    help = "Seed the database with departments"

    def handle(self, *args, **kwargs):
        departments = [
            "Department of Business Administration",
            "Department of Management",
            "Department of Real Estate",
            "Department of Tourism & Hospitality Management",
            "Department of Innovation & Entrepreneurship",
            "Department of Finance and Banking",
            "Department of Accounting",
            "Department of Marketing",
            "Department of Computer Science & Engineering",
            "Department of Computing & Information System (CIS)",
            "Department of Software Engineering",
            "Department of Environmental Science and Disaster Management",
            "Department of Multimedia & Creative Technology (MCT)",
            "Department of Information Technology and Management",
            "Department of Physical Education & Sports Science (PESS)",
            "Department of Information and Communication Engineering",
            "Department of Textile Engineering",
            "Department of Electrical & Electronic Engineering",
            "Department of Architecture",
            "Department of Civil Engineering",
            "Department of Pharmacy",
            "Department of Public Health",
            "Department of Nutrition & Food Engineering",
            "Department of Agricultural Science (AGS)",
            "Department of Genetic Engineering and Biotechnology",
            "Department of English",
            "Department of Law",
            "Department of Journalism & Mass Communication",
            "Department of Development Studies",
            "Department of Information Science and Library Management",
        ]

        for dept in departments:
            Department.objects.get_or_create(department_name=dept)

        self.stdout.write(self.style.SUCCESS("✅ Departments seeded successfully!"))
