from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("mainapp", "0060_reconcile_subject_faculty_mappings"),
    ]

    operations = [
        migrations.AddField(
            model_name="admissionresult",
            name="waiting_department",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Highest-preference eligible department whose seat was full and "
                    "whose waiting list still had capacity during allocation"
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="waiting_admission_results",
                to="mainapp.department",
            ),
        ),
    ]
