from django.urls import path
from .views import AllScrappedQuestionsView, questions_stats, total_questions, CreateExamAPIView, ExamQuestionListView, AddQuestionToExamView, ExamQuestionDetailView, AllExamsView, DeleteExamView
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
]