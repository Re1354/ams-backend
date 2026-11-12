from django.db import migrations, models


def populate_new_profile_and_acceptance_fields(apps, schema_editor):
    User = apps.get_model("mainapp", "User")
    AdmissionResult = apps.get_model("mainapp", "AdmissionResult")
    AdmissionReportSignatory = apps.get_model("mainapp", "AdmissionReportSignatory")

    for user in User.objects.filter(university_email__isnull=True).iterator():
        user.university_email = user.email
        user.save(update_fields=["university_email"])

    AdmissionResult.objects.filter(
        is_admitted=True,
        accepted_at__isnull=True,
    ).update(accepted_at=models.F("updated_at"))

    AdmissionReportSignatory.objects.filter(
        role="CONVENOR",
        affiliation_department__isnull=True,
    ).update(affiliation_department_id=models.F("department_id"))


class Migration(migrations.Migration):
    dependencies = [
        ("mainapp", "0064_admissionreportsignatory_affiliation_department_and_more"),
    ]

    operations = [
        migrations.RunPython(populate_new_profile_and_acceptance_fields, migrations.RunPython.noop),
    ]
