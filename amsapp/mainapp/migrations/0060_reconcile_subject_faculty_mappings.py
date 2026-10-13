# Generated data migration to reconcile and consolidate department subject mappings into faculty subject mappings

from django.db import migrations


def reconcile_subject_faculty_mappings(apps, schema_editor):
    SubjectDepartment = apps.get_model('mainapp', 'SubjectDepartment')
    SubjectFaculty = apps.get_model('mainapp', 'SubjectFaculty')
    FacultyDepartment = apps.get_model('mainapp', 'FacultyDepartment')
    Subject = apps.get_model('mainapp', 'Subject')

    # Build valid subject ID set to filter out any orphaned IDs
    valid_subject_ids = set(Subject.objects.values_list('id', flat=True))

    # Build mapping from department_id to faculty_id
    dept_to_faculty = {}
    for mapping in FacultyDepartment.objects.all():
        if mapping.department_ids:
            for dept_id in mapping.department_ids:
                dept_to_faculty[dept_id] = mapping.faculty_id

    # Reconcile SubjectDepartment rows into SubjectFaculty
    for sd in SubjectDepartment.objects.all():
        if not sd.subject_ids:
            continue
        faculty_id = dept_to_faculty.get(sd.department_id)
        if faculty_id:
            # Filter to valid subjects only
            clean_new_subjects = [s_id for s_id in sd.subject_ids if s_id in valid_subject_ids]
            sf, created = SubjectFaculty.objects.get_or_create(
                faculty_id=faculty_id,
                defaults={'subject_ids': sorted(list(set(clean_new_subjects)))}
            )
            if not created:
                existing = [s_id for s_id in (sf.subject_ids or []) if s_id in valid_subject_ids]
                merged = sorted(list(set(existing) | set(clean_new_subjects)))
                sf.subject_ids = merged
                sf.save()
        else:
            print(f"[Notice] Department ID {sd.department_id} has subject mappings but no parent faculty assigned.")

    # Deduplicate and clean all existing SubjectFaculty entries
    for sf in SubjectFaculty.objects.all():
        if sf.subject_ids:
            clean_ids = sorted(list(set([s_id for s_id in sf.subject_ids if s_id in valid_subject_ids])))
            if clean_ids != sf.subject_ids:
                sf.subject_ids = clean_ids
                sf.save()


def reverse_reconcile(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0059_exam_exam_type_exam_faculty_ref_exam_exam_type_idx'),
    ]

    operations = [
        migrations.RunPython(reconcile_subject_faculty_mappings, reverse_reconcile),
    ]
