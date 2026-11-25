from django.urls import path

from . import student_api

urlpatterns = [
    # Student portal (watcher)
    path("api/proctoring/sessions/start", student_api.StartSessionView.as_view(), name="proctoring-start"),
    path("api/proctoring/sessions/<int:session_id>/flags", student_api.FlagView.as_view(), name="proctoring-flag"),
    path("api/proctoring/sessions/<int:session_id>/end", student_api.EndSessionView.as_view(), name="proctoring-end"),
    path("api/proctoring/unlock", student_api.UnlockView.as_view(), name="proctoring-unlock"),
]

from . import admin_api  # noqa: E402

urlpatterns += [
    # Admin portal (Proctoring menu)
    path("api/proctoring/admin/sessions", admin_api.session_list, name="proctoring-admin-sessions"),
    path("api/proctoring/admin/sessions/<int:session_id>", admin_api.session_detail, name="proctoring-admin-session"),
    path("api/proctoring/admin/flags/<int:flag_id>/snapshot", admin_api.flag_snapshot, name="proctoring-admin-snapshot"),
    path("api/proctoring/admin/summary", admin_api.summary, name="proctoring-admin-summary"),
    path("api/proctoring/admin/ban", admin_api.ban, name="proctoring-admin-ban"),
    path("api/proctoring/admin/unban", admin_api.unban, name="proctoring-admin-unban"),
    path("api/proctoring/admin/unlock-code", admin_api.unlock_code, name="proctoring-admin-unlock-code"),
]
