from uuid import uuid4

from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import Role, User
from ..tokens import get_tokens_for_user


class UserProfileFieldsTests(APITestCase):
    def setUp(self):
        suffix = uuid4().hex[:8]
        role, _ = Role.objects.get_or_create(role_name="superadmin")
        admin = User.objects.create(
            username=f"profile-admin-{suffix}",
            email=f"profile-admin-{suffix}@example.com",
            university_email=f"profile-admin-{suffix}@example.com",
            password=make_password("Secret123!"),
            role=role,
        )
        self.role = role
        self.suffix = suffix
        self.client = APIClient()
        tokens = get_tokens_for_user(admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_create_user_stores_complete_profile_and_syncs_legacy_email(self):
        university_email = f"employee-{self.suffix}@diu.edu.bd"
        response = self.client.post(
            "/api/users/create/",
            {
                "username": f"employee-{self.suffix}",
                "password": "StrongPassword123!",
                "employee_id": f"EMP-{self.suffix}",
                "full_name": "Profile Employee",
                "designation": "Assistant Professor",
                "personal_email": f"personal-{self.suffix}@example.com",
                "university_email": university_email,
                "contact": "+8801700000000",
                "role_id": self.role.id,
                "access_type": "GLOBAL",
                "is_global_access": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username=f"employee-{self.suffix}")
        self.assertEqual(user.email, university_email)
        self.assertEqual(user.university_email, university_email)
        self.assertEqual(user.employee_id, f"EMP-{self.suffix}")
        self.assertEqual(user.full_name, "Profile Employee")
        self.assertEqual(user.designation, "Assistant Professor")
        self.assertEqual(user.contact, "+8801700000000")
        self.assertNotIn("password", response.data["data"])
