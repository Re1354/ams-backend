"""The local-only demo seed for the end-to-end check."""
from unittest import mock

from django.contrib.auth.hashers import check_password
from django.core.management import CommandError, call_command
from django.test import TestCase

from mainapp.models import AdmissionResult, Students
from proctoring import conduct
from proctoring.management.commands.proctoring_demo_seed import UNLOCK_CODE
from proctoring.models import ProctorSession, UnlockCode


class DemoSeedTests(TestCase):
    def run_seed(self):
        call_command("proctoring_demo_seed", stdout=mock.MagicMock())

    def test_refuses_a_database_that_is_not_local(self):
        from django.db import connection

        with mock.patch.dict(connection.settings_dict, {"HOST": "dpg-example.render.com"}):
            with self.assertRaises(CommandError):
                self.run_seed()
        self.assertFalse(Students.objects.filter(username="demo1").exists())

    def test_seed_builds_the_demo_and_can_run_twice(self):
        self.run_seed()
        self.run_seed()
        self.assertEqual(Students.objects.filter(username__startswith="demo").count(), 5)
        self.assertEqual(ProctorSession.objects.count(), 3)
        results = AdmissionResult.objects.filter(student__username__in=["demo2", "demo3", "demo4", "demo5"])
        self.assertEqual(results.count(), 4)
        exam = results.first().exam
        statuses = {
            s.username: conduct.conduct_for([s.id], [exam])[(s.id, exam.id)]["status"]
            for s in Students.objects.filter(username__in=["demo2", "demo3", "demo4"])
        }
        self.assertEqual(statuses, {"demo2": "reported", "demo3": "clear", "demo4": "not_monitored"})

    def test_seed_sets_the_local_support_unlock_code(self):
        self.run_seed()
        self.assertTrue(check_password(UNLOCK_CODE, UnlockCode.objects.get().code_hash))
