"""
Rename the old fabricated placeholder email to a clear "Not Entered" marker.

Students added without an email used to get a generated address of the form
"{lastname}notinserted@mail.com". Those now read as "Not Entered" to match the
new behaviour (see StudentsSerializer / frontend NOT_ENTERED_EMAIL).
"""

from django.db import migrations


PLACEHOLDER_SUFFIX = "notinserted@mail.com"
NOT_ENTERED = "Not Entered"


def rename_placeholder_emails(apps, schema_editor):
    Students = apps.get_model("mainapp", "Students")
    updated = Students.objects.filter(
        email__iendswith=PLACEHOLDER_SUFFIX
    ).update(email=NOT_ENTERED)
    print(f"  renamed {updated} placeholder email(s) to '{NOT_ENTERED}'.")


def revert(apps, schema_editor):
    # The original per-student address can't be reconstructed; leaving the
    # marker in place is the safe reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mainapp", "0050_dedupe_admission_results"),
    ]

    operations = [
        migrations.RunPython(rename_placeholder_emails, revert),
    ]
