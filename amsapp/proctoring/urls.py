from django.urls import path

from . import student_api

urlpatterns = [
    # Student portal (watcher)
    path("api/proctoring/sessions/start", student_api.StartSessionView.as_view(), name="proctoring-start"),
    path("api/proctoring/sessions/<int:session_id>/flags", student_api.FlagView.as_view(), name="proctoring-flag"),
    path("api/proctoring/sessions/<int:session_id>/end", student_api.EndSessionView.as_view(), name="proctoring-end"),
    path("api/proctoring/unlock", student_api.UnlockView.as_view(), name="proctoring-unlock"),
]
