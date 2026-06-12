from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mainapp', '0042_add_override_flag_to_admission_result'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='admissionresult',
            new_name='admission_r_is_over_8b945e_idx',
            old_name='admissionr_is_overrid_a2a9f5_idx',
        ),
        migrations.AddIndex(
            model_name='admissionresult',
            index=models.Index(fields=['department', 'configuration'], name='admission_dept_config_idx'),
        ),
        migrations.AddIndex(
            model_name='admissionresult',
            index=models.Index(fields=['status', 'result_status'], name='admission_status_result_idx'),
        ),
        migrations.AddIndex(
            model_name='admissionresult',
            index=models.Index(fields=['weighted_total_marks'], name='admission_weighted_idx'),
        ),
        migrations.AddIndex(
            model_name='admissionresult',
            index=models.Index(fields=['created_at'], name='admission_created_idx'),
        ),
        migrations.AddIndex(
            model_name='exam',
            index=models.Index(fields=['department', 'semester'], name='exam_dept_sem_idx'),
        ),
        migrations.AddIndex(
            model_name='exam',
            index=models.Index(fields=['created_at'], name='exam_created_idx'),
        ),
        migrations.AddIndex(
            model_name='examschedule',
            index=models.Index(fields=['start_time'], name='schedule_start_idx'),
        ),
        migrations.AddIndex(
            model_name='examschedule',
            index=models.Index(fields=['exam', 'start_time'], name='schedule_exam_start_idx'),
        ),
        migrations.AddIndex(
            model_name='examschedule',
            index=models.Index(fields=['is_active', 'start_time'], name='schedule_active_start_idx'),
        ),
        migrations.AddIndex(
            model_name='studentassignteacherexam',
            index=models.Index(fields=['teacher', 'schedule'], name='sta_teacher_schedule_idx'),
        ),
        migrations.AddIndex(
            model_name='studentassignteacherexam',
            index=models.Index(fields=['exam', 'created_at'], name='sta_exam_created_idx'),
        ),
        migrations.AddIndex(
            model_name='studentassignteacherexam',
            index=models.Index(fields=['schedule', 'created_at'], name='sta_schedule_created_idx'),
        ),
        migrations.AddIndex(
            model_name='students',
            index=models.Index(fields=['department_shortname', 'registration_semester'], name='students_dept_sem_idx'),
        ),
        migrations.AddIndex(
            model_name='students',
            index=models.Index(fields=['f_id'], name='students_fid_idx'),
        ),
        migrations.AddIndex(
            model_name='students',
            index=models.Index(fields=['created_at'], name='students_created_idx'),
        ),
        migrations.AddIndex(
            model_name='vivaassignment',
            index=models.Index(fields=['teacher', 'exam'], name='viva_teacher_exam_idx'),
        ),
        migrations.AddIndex(
            model_name='vivaassignment',
            index=models.Index(fields=['exam', 'created_at'], name='viva_exam_created_idx'),
        ),
        migrations.AddIndex(
            model_name='vivaassignment',
            index=models.Index(fields=['teacher', 'created_at'], name='viva_teacher_created_idx'),
        ),
        migrations.AddIndex(
            model_name='vivaassignment',
            index=models.Index(fields=['created_at'], name='viva_created_idx'),
        ),
        migrations.AddIndex(
            model_name='vivaassignment',
            index=models.Index(fields=['scheduled_at'], name='viva_scheduled_idx'),
        ),
    ]
