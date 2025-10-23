from django.urls import path
from .views import (
    AllScrappedQuestionsView, questions_stats, total_questions, CreateExamAPIView, 
    ExamQuestionListView, AddQuestionToExamView, ExamQuestionDetailView, AllExamsView, DeleteExamView,
    AllSchedulesView, ScheduleDetailView, create_exam_schedule,
    student_login, StudentAvailableExamsView, StudentExamQuestionsView, 
    submit_exam, get_exam_result, get_student_scheduled_exams, get_student_schedule, login_view, refresh_token_view, verify_token_view,
    get_all_roles, create_role, get_role_by_id, update_role, delete_role,
    get_all_users, create_user, get_user_by_id, update_user, delete_user, get_all_teachers
)
from .views import upload_docx_scrape_multipart
from .views.students import (
    get_all_students, create_student, get_student_by_id, update_student, delete_student
)
from .views.menus import (
    all_menus, role_menus, assign_menus_to_role, remove_menu_from_role, user_menus,
    create_menu, update_menu, delete_menu
)
from .views.departments import (
    get_all_departments, create_department, get_department_by_id, 
    update_department_full, update_department_partial, delete_department
)
from .views.subjects import (
    get_all_subjects, create_subject, get_subject_by_id,
    update_subject, delete_subject
)
from .views.subject_departments import (
    get_all_subject_departments, create_subject_department, get_subject_department_by_id,
    get_subjects_by_department, update_subject_department, add_subjects_to_department,
    remove_subjects_from_department, delete_subject_department
)
from .views.exam_generation import generate_exam, save_generated_exam
from .views.student_assign_teacher_exam import (
    assign_students_bulk, assign_student_single, get_all_assignments, 
    delete_assignment, delete_assignments_bulk, get_available_schedules
)
from .views.results import (
    toggle_exam_publication, get_student_exam_result_enhanced,
    get_all_results_by_teacher, get_published_exams
)
from .views.blocklist_question import (
    block_question as block_question_new, get_all_blocked_questions, restore_blocked_question, delete_blocked_question, block_question_by_id
)
from .views.viva_rubrics import (
    create_viva_rubrics, get_all_viva_rubrics, get_viva_rubrics_by_id,
    get_viva_rubrics_by_department, update_viva_rubrics, delete_viva_rubrics
)
from .views.marks_distribution import (
    create_marks_distribution, get_all_marks_distribution, get_marks_distribution_by_id,
    get_marks_distribution_by_department, update_marks_distribution, delete_marks_distribution
)
from .views.viva_assign import (
    create_viva_assignment, get_all_viva_assignments, delete_viva_assignment
)
from .views.viva_marks import (
    add_viva_marks, delete_viva_marks
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
    path('api/students/', get_all_students, name='get-all-students'),
    path('api/students/create/', create_student, name='create-student'),
    path('api/students/<int:student_id>/', get_student_by_id, name='get-student-by-id'),
    path('api/students/<int:student_id>/update/', update_student, name='update-student'),
    path('api/students/<int:student_id>/delete/', delete_student, name='delete-student'),
    
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
    path('api/student/<int:student_id>/scheduled-exams/', get_student_scheduled_exams, name='get-student-scheduled-exams'),
    path('api/student/<int:student_id>/schedule/', get_student_schedule, name='get-student-schedule'),
    
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
    path('api/users/teachers/', get_all_teachers, name='get-all-teachers'),
    path('api/users/create/', create_user, name='create-user'),
    path('api/users/<int:user_id>/', get_user_by_id, name='get-user-by-id'),
    path('api/users/<int:user_id>/update/', update_user, name='update-user'),
    path('api/users/<int:user_id>/delete/', delete_user, name='delete-user'),
    
    # Menu Management API
    path('api/menus/', all_menus, name='all-menus'),
    path('api/menus/create/', create_menu, name='create-menu'),
    path('api/menus/<int:menu_id>/update/', update_menu, name='update-menu'),
    path('api/menus/<int:menu_id>/delete/', delete_menu, name='delete-menu'),
    path('api/menus/user/', user_menus, name='user-menus'),
    path('api/roles/<int:role_id>/menus/', role_menus, name='role-menus'),
    path('api/roles/assign-menus/', assign_menus_to_role, name='assign-menus-to-role'),
    path('api/roles/<int:role_id>/menus/<int:menu_id>/remove/', remove_menu_from_role, name='remove-menu-from-role'),
    
    # Department Management API
    path('api/departments/', get_all_departments, name='get-all-departments'),
    path('api/departments/create/', create_department, name='create-department'),
    path('api/departments/<int:department_id>/', get_department_by_id, name='get-department-by-id'),
    path('api/departments/<int:department_id>/update/', update_department_full, name='update-department-full'),
    path('api/departments/<int:department_id>/update/', update_department_partial, name='update-department-partial'),
    path('api/departments/<int:department_id>/delete/', delete_department, name='delete-department'),
    
    # Subject Management API
    path('api/subjects/', get_all_subjects, name='get-all-subjects'),
    path('api/subjects/create/', create_subject, name='create-subject'),
    path('api/subjects/<int:subject_id>/', get_subject_by_id, name='get-subject-by-id'),
    path('api/subjects/<int:subject_id>/update/', update_subject, name='update-subject'),
    path('api/subjects/<int:subject_id>/delete/', delete_subject, name='delete-subject'),
    
    # Subject-Department Mapping API
    path('api/subject-departments/', get_all_subject_departments, name='get-all-subject-departments'),
    path('api/subject-departments/create/', create_subject_department, name='create-subject-department'),
    path('api/subject-departments/<int:mapping_id>/', get_subject_department_by_id, name='get-subject-department-by-id'),
    path('api/subject-departments/department/<int:department_id>/', get_subjects_by_department, name='get-subjects-by-department'),
    path('api/subject-departments/<int:mapping_id>/update/', update_subject_department, name='update-subject-department'),
    path('api/subject-departments/<int:mapping_id>/add-subjects/', add_subjects_to_department, name='add-subjects-to-department'),
    path('api/subject-departments/<int:mapping_id>/remove-subjects/', remove_subjects_from_department, name='remove-subjects-from-department'),
    path('api/subject-departments/<int:mapping_id>/delete/', delete_subject_department, name='delete-subject-department'),
    
    # Exam Generation API
    path('api/exams/generate/', generate_exam, name='generate-exam'),
    path('api/exams/save-generated/', save_generated_exam, name='save-generated-exam'),
    
    # Student Assignment API
    path('api/student-assignments/', get_all_assignments, name='get-all-assignments'),
    path('api/student-assignments/assign-bulk/', assign_students_bulk, name='assign-students-bulk'),
    path('api/student-assignments/assign-single/', assign_student_single, name='assign-student-single'),
    path('api/student-assignments/<int:assignment_id>/delete/', delete_assignment, name='delete-assignment'),
    path('api/student-assignments/delete-bulk/', delete_assignments_bulk, name='delete-assignments-bulk'),
    path('api/student-assignments/available-schedules/', get_available_schedules, name='get-available-schedules'),
    
    # Results Management API
    path('api/result/published/', toggle_exam_publication, name='toggle-exam-publication'),
    path('api/published-exams/', get_published_exams, name='get-published-exams'),
    path('api/student/exam/<int:exam_id>/result/<int:student_id>/', get_student_exam_result_enhanced, name='get-student-exam-result-enhanced'),
    path('api/get-all-results-by-teacher/<int:teacher_id>/', get_all_results_by_teacher, name='get-all-results-by-teacher'),
    
    # Blocklist Question Management API
    path('api/question/block/', block_question_new, name='block-question-new'),
    path('api/question/block/<int:question_id>/', block_question_by_id, name='block-question-by-id'),
    path('api/get-all-blocked-questions/', get_all_blocked_questions, name='get-all-blocked-questions'),
    path('api/blocked-question/<int:question_id>/restore/', restore_blocked_question, name='restore-blocked-question'),
    path('api/blocked-question/<int:question_id>/delete/', delete_blocked_question, name='delete-blocked-question'),
    
    # Viva Rubrics Management API
    path('api/create-rubrics/', create_viva_rubrics, name='create-viva-rubrics'),
    path('api/all-rubrics/', get_all_viva_rubrics, name='get-all-viva-rubrics'),
    path('api/rubrics/<int:rubrics_id>/', get_viva_rubrics_by_id, name='get-viva-rubrics-by-id'),
    path('api/rubrics/department/<int:department_id>/', get_viva_rubrics_by_department, name='get-viva-rubrics-by-department'),
    path('api/rubrics/<int:rubrics_id>/update/', update_viva_rubrics, name='update-viva-rubrics'),
    path('api/rubrics/<int:rubrics_id>/delete/', delete_viva_rubrics, name='delete-viva-rubrics'),
    
    # Marks Distribution Management API  
    path('api/create-marks-distribution/', create_marks_distribution, name='create-marks-distribution'),
    path('api/all-marks-distribution/', get_all_marks_distribution, name='get-all-marks-distribution'),
    path('api/marks-distribution/<int:marks_distribution_id>/', get_marks_distribution_by_id, name='get-marks-distribution-by-id'),
    path('api/marks-distribution/department/<int:department_id>/', get_marks_distribution_by_department, name='get-marks-distribution-by-department'),
    path('api/marks-distribution/<int:marks_distribution_id>/update/', update_marks_distribution, name='update-marks-distribution'),
    path('api/marks-distribution/<int:marks_distribution_id>/delete/', delete_marks_distribution, name='delete-marks-distribution'),

    # Viva Assignment Management API
    path('api/viva-assignments/', get_all_viva_assignments, name='get-all-viva-assignments'),
    path('api/viva-assignments/create/', create_viva_assignment, name='create-viva-assignment'),
    path('api/viva-assignments/<int:assignment_id>/delete/', delete_viva_assignment, name='delete-viva-assignment'),

    # Viva Marks Management API
    path('api/add-viva-marks/<int:student_id>/', add_viva_marks, name='add-viva-marks'),
    path('api/delete-viva-marks/<int:student_id>/', delete_viva_marks, name='delete-viva-marks'),
    # Document scraper upload
    path('api/scrape-docx/', upload_docx_scrape_multipart, name='upload-docx-scrape'),
]