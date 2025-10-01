from django.core.management.base import BaseCommand
from mainapp.models import Department


class Command(BaseCommand):
    help = "Seed the database with departments"

    def handle(self, *args, **kwargs):
        departments = [
            ("Department of Business Administration", "BBA"),
            ("Department of Management", "MGT"),
            ("Department of Real Estate", "RE"),
            ("Department of Tourism & Hospitality Management", "THM"),
            ("Department of Innovation & Entrepreneurship", "IE"),
            ("Department of Finance and Banking", "FNB"),
            ("Department of Accounting", "ACC"),
            ("Department of Marketing", "MKT"),
            ("Department of Computer Science & Engineering", "CSE"),
            ("Department of Computing & Information System (CIS)", "CIS"),
            ("Department of Software Engineering", "SE"),
            ("Department of Environmental Science and Disaster Management", "ESDM"),
            ("Department of Multimedia & Creative Technology (MCT)", "MCT"),
            ("Department of Information Technology and Management", "ITM"),
            ("Department of Physical Education & Sports Science (PESS)", "PESS"),
            ("Department of Information and Communication Engineering", "ICE"),
            ("Department of Textile Engineering", "TE"),
            ("Department of Electrical & Electronic Engineering", "EEE"),
            ("Department of Architecture", "ARCH"),
            ("Department of Civil Engineering", "CE"),
            ("Department of Pharmacy", "PHARM"),
            ("Department of Public Health", "PH"),
            ("Department of Nutrition & Food Engineering", "NFE"),
            ("Department of Agricultural Science (AGS)", "AGS"),
            ("Department of Genetic Engineering and Biotechnology", "GEB"),
            ("Department of English", "ENG"),
            ("Department of Law", "LAW"),
            ("Department of Journalism & Mass Communication", "JMC"),
            ("Department of Development Studies", "DS"),
            ("Department of Information Science and Library Management", "ISLM"),
        ]

        for full_name, short_name in departments:
            Department.objects.get_or_create(
                department_name=full_name,
                defaults={'department_shortname': short_name}
            )

        self.stdout.write(self.style.SUCCESS("✅ Departments seeded successfully!"))