from django.urls import path
from .views import (
    AllScrappedQuestionsView, questions_stats, total_questions, CreateExamAPIView, 
    ExamQuestionListView, AddQuestionToExamView, ExamQuestionDetailView, AllExamsView, DeleteExamView,
    AllStudentsView, StudentDetailView, AllSchedulesView, ScheduleDetailView, create_exam_schedule,
    student_login, StudentAvailableExamsView, StudentExamQuestionsView, 
    submit_exam, get_exam_result, calculate_exam_result
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
    path('api/exam/<int:exam_id>/results/', calculate_exam_result, name='calculate-exam-result'),
]