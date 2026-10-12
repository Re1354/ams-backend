# Generated data migration to link existing department-level records to parent faculties

from django.db import migrations


def populate_faculty_level_records(apps, schema_editor):
    SubjectDepartment = apps.get_model('mainapp', 'SubjectDepartment')
    SubjectFaculty = apps.get_model('mainapp', 'SubjectFaculty')
    VivaRubrics = apps.get_model('mainapp', 'VivaRubrics')
    MarksDistribution = apps.get_model('mainapp', 'MarksDistribution')
    FacultyDepartment = apps.get_model('mainapp', 'FacultyDepartment')

    # Build mapping from department_id to faculty_id
    dept_to_faculty = {}
    for mapping in FacultyDepartment.objects.all():
        if mapping.department_ids:
            for dept_id in mapping.department_ids:
                dept_to_faculty[dept_id] = mapping.faculty_id

    # 1. Backfill SubjectFaculty from existing SubjectDepartment
    for sd in SubjectDepartment.objects.all():
        faculty_id = dept_to_faculty.get(sd.department_id)
        if faculty_id and sd.subject_ids:
            sf, created = SubjectFaculty.objects.get_or_create(
                faculty_id=faculty_id,
                defaults={'subject_ids': list(sd.subject_ids)}
            )
            if not created:
                # Merge subjects
                existing_subjects = set(sf.subject_ids or [])
                new_subjects = set(sd.subject_ids or [])
                sf.subject_ids = list(existing_subjects | new_subjects)
                sf.save()

    # 2. Backfill VivaRubrics faculty
    for rubric in VivaRubrics.objects.filter(faculty__isnull=True, department__isnull=False):
        faculty_id = dept_to_faculty.get(rubric.department_id)
        if faculty_id:
            rubric.faculty_id = faculty_id
            rubric.save()

    # 3. Backfill MarksDistribution faculty
    for dist in MarksDistribution.objects.filter(faculty__isnull=True, department__isnull=False):
        faculty_id = dept_to_faculty.get(dist.department_id)
        if faculty_id:
            dist.faculty_id = faculty_id
            dist.save()


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0057_marksdistribution_faculty_vivarubrics_faculty_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_faculty_level_records, reverse_populate),
    ]
