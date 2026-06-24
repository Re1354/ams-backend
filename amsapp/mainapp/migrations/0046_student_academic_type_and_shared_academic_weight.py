from django.db import migrations, models
from django.db.models import F


def backfill_academic_type_and_weights(apps, schema_editor):
    Students = apps.get_model('mainapp', 'Students')
    MarksDistribution = apps.get_model('mainapp', 'MarksDistribution')

    Students.objects.filter(diploma__gt=0).update(
        academic_type='DIPLOMA',
        hsc=0,
    )
    Students.objects.exclude(diploma__gt=0).update(
        academic_type='HSC',
        diploma=0,
    )
    MarksDistribution.objects.update(diploma=F('hsc'))


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0045_examdraft'),
    ]

    operations = [
        migrations.AddField(
            model_name='students',
            name='academic_type',
            field=models.CharField(
                choices=[('HSC', 'HSC'), ('DIPLOMA', 'Diploma')],
                default='HSC',
                help_text='Whether the student uses HSC GPA or Diploma CGPA',
                max_length=20,
            ),
        ),
        migrations.RunPython(
            backfill_academic_type_and_weights,
            migrations.RunPython.noop,
        ),
    ]
