from uuid import uuid4

from django.contrib.auth.hashers import make_password
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import Department, Menu, Role, RoleMenu, Subject, SubjectDepartment, User
from ..tokens import get_tokens_for_user


class ManagementMenuPermissionTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        suffix = uuid4().hex[:8]

        self.superadmin_role, _ = Role.objects.get_or_create(role_name="superadmin")
        self.manager_role = Role.objects.create(role_name=f"Manager {suffix}")
        self.target_role = Role.objects.create(role_name=f"Target {suffix}")

        self.superadmin_user = self.create_user("superadmin", self.superadmin_role, suffix)
        self.manager_user = self.create_user("manager", self.manager_role, suffix)

        self.department_menu = self.create_menu(
            "Department Management",
            "/department-management",
            "DepartmentManagement",
        )
        self.subject_menu = self.create_menu(
            "Subject Management",
            "/subject-management",
            "SubjectManagement",
        )
        self.mapping_menu = self.create_menu(
            "Subject Department Mapping",
            "/subject-department-mapping",
            "SubjectDepartmentMapping",
        )
        self.menu_access_menu = self.create_menu(
            "Menu Access Management",
            "/menu-access-management",
            "MenuAccessManagement",
        )
        self.extra_menu = self.create_menu(
            "Extra Menu",
            f"/extra-{suffix}",
            "ExtraMenu",
        )

    def create_user(self, prefix, role, suffix):
        return User.objects.create(
            username=f"{prefix}-{suffix}",
            email=f"{prefix}-{suffix}@test.com",
            password=make_password("admin123"),
            role=role,
        )

    def create_menu(self, label, link, component):
        return Menu.objects.create(
            label=label,
            icon="Settings",
            link=link,
            component=component,
        )

    def authenticate(self, user):
        tokens = get_tokens_for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def grant(self, menu, permissions):
        RoleMenu.objects.update_or_create(
            role=self.manager_role,
            menu=menu,
            defaults={"permissions": permissions},
        )

    def test_department_permissions_control_create_edit_and_delete(self):
        self.grant(
            self.department_menu,
            {"read": True, "write": True, "edit": True, "delete": True},
        )
        self.authenticate(self.manager_user)

        create_response = self.client.post(
            "/api/departments/create/",
            {
                "department_name": "Computer Science",
                "department_shortname": "CSE",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        department_id = create_response.data["data"]["id"]
        update_response = self.client.put(
            f"/api/departments/{department_id}/update/",
            {
                "department_name": "Computer Science and Engineering",
                "department_shortname": "CSE",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        delete_response = self.client.delete(f"/api/departments/{department_id}/delete/")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)

    def test_department_write_actions_reject_missing_permissions(self):
        self.grant(
            self.department_menu,
            {"read": True, "write": False, "edit": False, "delete": False},
        )
        department = Department.objects.create(
            department_name="Business Administration",
            department_shortname="BBA",
        )
        self.authenticate(self.manager_user)

        create_response = self.client.post(
            "/api/departments/create/",
            {
                "department_name": "Software Engineering",
                "department_shortname": "SWE",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

        update_response = self.client.put(
            f"/api/departments/{department.id}/update/",
            {
                "department_name": "Business Studies",
                "department_shortname": "BBS",
            },
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)

        delete_response = self.client.delete(f"/api/departments/{department.id}/delete/")
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_subject_permissions_control_create_edit_and_delete(self):
        self.grant(
            self.subject_menu,
            {"read": True, "write": True, "edit": True, "delete": True},
        )
        self.authenticate(self.manager_user)

        create_response = self.client.post(
            "/api/subjects/create/",
            {"subject_name": "Mathematics"},
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        subject_id = create_response.data["data"]["id"]
        update_response = self.client.put(
            f"/api/subjects/{subject_id}/update/",
            {"subject_name": "Advanced Mathematics"},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        delete_response = self.client.delete(f"/api/subjects/{subject_id}/delete/")
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)

    def test_subject_mapping_permissions_control_mutations(self):
        self.grant(
            self.mapping_menu,
            {"read": True, "write": True, "edit": True, "delete": True},
        )
        department = Department.objects.create(
            department_name="Electrical Engineering",
            department_shortname="EEE",
        )
        first_subject = Subject.objects.create(subject_name="Physics")
        second_subject = Subject.objects.create(subject_name="Circuits")
        self.authenticate(self.manager_user)

        create_response = self.client.post(
            "/api/subject-departments/create/",
            {
                "department": department.id,
                "subject_ids": [first_subject.id],
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        mapping_id = create_response.data["data"]["id"]
        add_response = self.client.post(
            f"/api/subject-departments/{mapping_id}/add-subjects/",
            {"subject_ids": [second_subject.id]},
            format="json",
        )
        self.assertEqual(add_response.status_code, status.HTTP_200_OK)

        remove_response = self.client.post(
            f"/api/subject-departments/{mapping_id}/remove-subjects/",
            {"subject_ids": [second_subject.id]},
            format="json",
        )
        self.assertEqual(remove_response.status_code, status.HTTP_200_OK)

        update_response = self.client.patch(
            f"/api/subject-departments/{mapping_id}/update/",
            {"subject_ids": [first_subject.id, second_subject.id]},
            format="json",
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)

        delete_response = self.client.delete(
            f"/api/subject-departments/{mapping_id}/delete/"
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)

    def test_menu_access_permissions_control_assignment_and_removal(self):
        self.grant(
            self.menu_access_menu,
            {"read": True, "write": True, "edit": False, "delete": True},
        )
        self.authenticate(self.manager_user)

        assign_response = self.client.post(
            "/api/roles/assign-menus/",
            {
                "role_id": self.target_role.id,
                "menus": [
                    {
                        "menu_id": self.extra_menu.id,
                        "permissions": {
                            "read": True,
                            "write": True,
                            "edit": False,
                            "delete": False,
                        },
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            RoleMenu.objects.filter(role=self.target_role, menu=self.extra_menu).exists()
        )

        remove_response = self.client.delete(
            f"/api/roles/{self.target_role.id}/menus/{self.extra_menu.id}/remove/"
        )
        self.assertEqual(remove_response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            RoleMenu.objects.filter(role=self.target_role, menu=self.extra_menu).exists()
        )

    def test_menu_access_write_actions_reject_missing_permissions(self):
        self.grant(
            self.menu_access_menu,
            {"read": True, "write": False, "edit": False, "delete": False},
        )
        RoleMenu.objects.create(
            role=self.target_role,
            menu=self.extra_menu,
            permissions={"read": True, "write": False, "edit": False, "delete": False},
        )
        self.authenticate(self.manager_user)

        assign_response = self.client.post(
            "/api/roles/assign-menus/",
            {
                "role_id": self.target_role.id,
                "menus": [
                    {
                        "menu_id": self.department_menu.id,
                        "permissions": {
                            "read": True,
                            "write": False,
                            "edit": False,
                            "delete": False,
                        },
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_403_FORBIDDEN)

        remove_response = self.client.delete(
            f"/api/roles/{self.target_role.id}/menus/{self.extra_menu.id}/remove/"
        )
        self.assertEqual(remove_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_superadmin_bypasses_menu_permission_rows(self):
        self.authenticate(self.superadmin_user)

        department_response = self.client.post(
            "/api/departments/create/",
            {
                "department_name": "Law",
                "department_shortname": "LAW",
            },
            format="json",
        )
        self.assertEqual(department_response.status_code, status.HTTP_201_CREATED)

        assign_response = self.client.post(
            "/api/roles/assign-menus/",
            {
                "role_id": self.target_role.id,
                "menus": [
                    {
                        "menu_id": self.extra_menu.id,
                        "permissions": {
                            "read": True,
                            "write": False,
                            "edit": False,
                            "delete": False,
                        },
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)
