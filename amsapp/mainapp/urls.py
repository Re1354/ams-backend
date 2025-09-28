from django.urls import path
from .views import (
    AllScrappedQuestionsView, questions_stats, total_questions, CreateExamAPIView, 
    ExamQuestionListView, AddQuestionToExamView, ExamQuestionDetailView, AllExamsView, DeleteExamView,
    AllStudentsView, StudentDetailView, AllSchedulesView, ScheduleDetailView, create_exam_schedule,
    student_login, StudentAvailableExamsView, StudentExamQuestionsView, 
    submit_exam, get_exam_result, login_view, refresh_token_view, verify_token_view,
    get_all_roles, create_role, get_role_by_id, update_role, delete_role,
    get_all_users, create_user, get_user_by_id, update_user, delete_user
)
from .api_info import api_info, home

app_name = 'mainapp'

urlpatterns = [
    # Home page
    path('', home, name='home'),
    
    # API Info
    path('api/info/', api_info, name='api-info'),
    
    # Questions API
    path('api/all-scrapped-questions/', AllScrappedQuestionsView.as_view(), name='all-scrapped-questions'),
    path('api/questions-stats/', questions_stats, name='questions-stats'),
    path('api/total-questions/', total_questions, name='total-questions'),
    
    # Exam API
    path('api/all-exams/', AllExamsView.as_view(), name='all-exams'),
    path('api/create-exam/', CreateExamAPIView.as_view(), name='create-exam'),
    path('api/exam-questions/<int:exam_id>/', ExamQuestionListView.as_view(), name='exam-questions'),
    path('api/exam-questions/<int:exam_id>/add/', AddQuestionToExamView.as_view(), name='add-question-to-exam'),
    path('api/exam-questions/<int:exam_id>/question/<int:question_id>/', ExamQuestionDetailView.as_view(), name='exam-question-detail'),
    path('api/exam-questions/<int:exam_id>/delete/', DeleteExamView.as_view(), name='delete-exam'),
    
    # Student Management API
    path('api/students/', AllStudentsView.as_view(), name='all-students'),
    path('api/students/<int:student_id>/', StudentDetailView.as_view(), name='student-detail'),
    
    # Schedule Management API
    path('api/schedules/', AllSchedulesView.as_view(), name='all-schedules'),
    path('api/schedules/create/', create_exam_schedule, name='create-exam-schedule'),
    path('api/schedules/<int:schedule_id>/', ScheduleDetailView.as_view(), name='schedule-detail'),
    
    # Student App API (for React app)
    path('api/student/login/', student_login, name='student-login'),
    path('api/student/available-exams/', StudentAvailableExamsView.as_view(), name='student-available-exams'),
    path('api/student/exam/<int:exam_id>/questions/', StudentExamQuestionsView.as_view(), name='student-exam-questions'),
    path('api/student/exam/<int:exam_id>/submit/', submit_exam, name='submit-exam'),
    path('api/student/exam/<int:exam_id>/result/<int:student_id>/', get_exam_result, name='get-exam-result'),
    
    # Authentication API
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/refresh/', refresh_token_view, name='refresh-token'),
    path('api/auth/verify/', verify_token_view, name='verify-token'),
    
    # Roles API
    path('api/roles/', get_all_roles, name='get-all-roles'),
    path('api/roles/create/', create_role, name='create-role'),
    path('api/roles/<int:role_id>/', get_role_by_id, name='get-role-by-id'),
    path('api/roles/<int:role_id>/update/', update_role, name='update-role'),
    path('api/roles/<int:role_id>/delete/', delete_role, name='delete-role'),
    
    # Users API
    path('api/users/', get_all_users, name='get-all-users'),
    path('api/users/create/', create_user, name='create-user'),
    path('api/users/<int:user_id>/', get_user_by_id, name='get-user-by-id'),
    path('api/users/<int:user_id>/update/', update_user, name='update-user'),
    path('api/users/<int:user_id>/delete/', delete_user, name='delete-user'),
]