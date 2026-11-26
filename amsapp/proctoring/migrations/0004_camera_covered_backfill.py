"""Sessions recorded before the covered-camera rule: give them the same status as new ones.

A session with a CAMERA_OFF flag (camera covered or disconnected) is marked camera_off,
and reported from the counted flag that brought it above one counted flag. Sessions
that are already reported keep their time. Data only; no table changes.
"""
from django.db import migrations


def mark_camera_covered_sessions(apps, schema_editor):
    ProctorSession = apps.get_model("proctoring", "ProctorSession")
    Flag = apps.get_model("proctoring", "Flag")
    for session in ProctorSession.objects.filter(flags__code="CAMERA_OFF").distinct():
        changes = {}
        if not session.camera_off:
            changes["camera_off"] = True
        if session.reported_at is None:
            count, covered = 0, False
            for flag in Flag.objects.filter(session_id=session.pk, counted=True).order_by("created_at", "id"):
                count += 1
                covered = covered or flag.code == "CAMERA_OFF"
                if covered and count > 1:
                    changes["reported_at"] = flag.created_at
                    break
        if changes:
            ProctorSession.objects.filter(pk=session.pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("proctoring", "0003_session_camera_off")]

    operations = [migrations.RunPython(mark_camera_covered_sessions, migrations.RunPython.noop)]
