from django.test.runner import DiscoverRunner


class MainAppDiscoverRunner(DiscoverRunner):
    """
    Keep `manage.py test` stable from the project root.

    Django's default discovery from "." can collide with the `mainapp/tests`
    package on this Windows setup, so default unlabeled runs to the app test
    package explicitly.
    """

    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels:
            test_labels = ["mainapp.tests", "proctoring.tests"]
        return super().build_suite(test_labels, **kwargs)
