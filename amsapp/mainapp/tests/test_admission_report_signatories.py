from uuid import uuid4

from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    AdmissionReportSignatory,
    Department,
    Faculty,
    FacultyDepartment,
    Role,
    User,
)
from ..tokens import get_tokens_for_user
from ..views.admission_report import normalize_faculty_label


class AdmissionReportSignatoryTests(APITestCase):
    def setUp(self):
        suffix = uuid4().hex[:8]
        role, _ = Role.objects.get_or_create(role_name="superadmin")
        user = User.objects.create(
            username=f"signatory-admin-{suffix}",
            email=f"signatory-admin-{suffix}@example.com",
            password=make_password("Secret123!"),
            role=role,
        )
        self.client = APIClient()
        tokens = get_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        self.department = Department.objects.create(
            department_name=f"Department of Computer Science & Engineering {suffix}",
            department_shortname=f"CSE-{suffix}",
        )
        self.faculty = Faculty.objects.create(
            faculty_name=f"Faculty of Science and Information Technology {suffix}",
            faculty_shortname=f"FSIT-{suffix}",
        )
        FacultyDepartment.objects.create(
            faculty=self.faculty,
            department_ids=[self.department.id],
        )

    def test_upserts_and_filters_department_and_faculty_signatories(self):
        payloads = [
            {
                "role": "CONVENOR",
                "name": "Convenor Name",
                "designation": "Assistant Professor",
                "department": self.department.id,
                "faculty": None,
            },
            {
                "role": "DEPARTMENT_HEAD",
                "name": "Head Name",
                "designation": "Professor & Head",
                "department": self.department.id,
                "faculty": None,
            },
            {
                "role": "DEAN",
                "name": "Dean Name",
                "designation": "Dean & Professor",
                "department": None,
                "faculty": self.faculty.id,
            },
        ]
        for payload in payloads:
            response = self.client.post(
                "/api/admission/report-signatories/", payload, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(
            "/api/admission/report-signatories/",
            {
                "department_id": self.department.id,
                "faculty_id": self.faculty.id,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item["role"] for item in response.data["data"]},
            {"CONVENOR", "DEPARTMENT_HEAD", "DEAN"},
        )

        updated = {**payloads[0], "name": "Updated Convenor"}
        update_response = self.client.post(
            "/api/admission/report-signatories/", updated, format="json"
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            AdmissionReportSignatory.objects.filter(
                role="CONVENOR", department=self.department
            ).count(),
            1,
        )
        self.assertEqual(update_response.data["data"]["name"], "Updated Convenor")

    def test_faculty_label_removes_repeated_prefixes(self):
        self.assertEqual(
            normalize_faculty_label(
                "Faculty of Faculty of Science and Information Technology"
            ),
            "Science and Information Technology",
        )
