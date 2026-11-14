import tempfile
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from ..models import Department, Role, User


class CurrentUserProfileTestCase(APITestCase):
    def setUp(self):
        suffix = uuid4().hex[:8]
        self.role = Role.objects.create(role_name=f"profile-role-{suffix}")
        self.department = Department.objects.create(
            department_name=f"Profile Department {suffix}",
            department_shortname=f"P{suffix[:4]}",
        )
        self.user = User.objects.create(
            username=f"profile-user-{suffix}",
            email=f"profile-user-{suffix}@example.com",
            university_email=f"profile-user-{suffix}@example.com",
            password="unused",
            role=self.role,
            department=self.department,
        )
        token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_get_current_profile(self):
        response = self.client.get("/api/users/profile/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["id"], self.user.id)
        self.assertEqual(
            response.data["data"]["department_details"]["id"],
            self.department.id,
        )

    def test_update_profile_fields_without_changing_access_scope(self):
        response = self.client.patch(
            "/api/users/profile/",
            {
                "full_name": "Updated Profile Name",
                "designation": "Assistant Professor",
                "contact": "01700000000",
                "personal_email": "personal@example.com",
                "university_email": "updated.profile@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Updated Profile Name")
        self.assertEqual(self.user.email, "updated.profile@example.com")
        self.assertEqual(self.user.department_id, self.department.id)
        self.assertEqual(self.user.role_id, self.role.id)

    def test_upload_profile_image(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                image = SimpleUploadedFile(
                    "avatar.png",
                    b"small-profile-image",
                    content_type="image/png",
                )
                response = self.client.patch(
                    "/api/users/profile/",
                    {"image": image},
                    format="multipart",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("/media/user_profiles/", response.data["data"]["image"])

    def test_reject_non_image_profile_upload(self):
        upload = SimpleUploadedFile(
            "profile.txt",
            b"not-an-image",
            content_type="text/plain",
        )
        response = self.client.patch(
            "/api/users/profile/",
            {"image": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data["errors"])
