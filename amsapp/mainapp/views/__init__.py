# Import all views to make them available when importing from views
from .questions import AllScrappedQuestionsView, questions_stats, total_questions
from .questions import insert_scrapped_questions
from .exams import (
    CreateExamAPIView, AllExamsView, ExamQuestionListView, AddQuestionToExamView,
    ExamQuestionDetailView, DeleteExamView
)
from .students import get_all_students, create_student, get_student_by_id, update_student, delete_student
from .schedules import AllSchedulesView, create_exam_schedule, ScheduleDetailView
from .student_app import (
    student_login, StudentAvailableExamsView, StudentExamQuestionsView, 
    submit_exam, get_exam_result, calculate_exam_result, calculate_exam_result_helper,
    get_student_scheduled_exams, get_student_schedule
)
from .auth import login_view, refresh_token_view, verify_token_view
from .roles import get_all_roles, create_role, get_role_by_id, update_role, delete_role
from .users import get_all_users, create_user, get_user_by_id, update_user, delete_user, get_all_teachers
from .student_assign_teacher_exam import (
    assign_students_bulk, assign_student_single, get_all_assignments, 
    delete_assignment, delete_assignments_bulk, get_available_schedules
)
from .results import (
    toggle_exam_publication, get_student_exam_result_enhanced,
    get_all_results_by_teacher, get_published_exams
)
from .blocklist_question import (
    block_question, get_all_blocked_questions, restore_blocked_question, delete_blocked_question, block_question_by_id
)
from .viva_rubrics import (
    create_viva_rubrics, get_all_viva_rubrics, get_viva_rubrics_by_id,
    get_viva_rubrics_by_department, update_viva_rubrics, delete_viva_rubrics
)
from .marks_distribution import (
    create_marks_distribution, get_all_marks_distribution, get_marks_distribution_by_id,
    get_marks_distribution_by_department, update_marks_distribution, delete_marks_distribution
)
from .viva_assign import (
    create_viva_assignment, get_all_viva_assignments, delete_viva_assignment
)
from .viva_marks import (
    add_viva_marks, delete_viva_marks
)
from .scrapper import upload_docx_scrape_multipart

# Make all views available when importing from mainapp.views
__all__ = [
    # Questions
    'AllScrappedQuestionsView', 'questions_stats', 'total_questions',
    
    # Exams
    'CreateExamAPIView', 'AllExamsView', 'ExamQuestionListView', 
    'AddQuestionToExamView', 'ExamQuestionDetailView', 'DeleteExamView',
    
    # Students
    'get_all_students', 'create_student', 'get_student_by_id', 'update_student', 'delete_student',
    
    # Schedules
    'AllSchedulesView', 'create_exam_schedule', 'ScheduleDetailView',
    
    # Student App
    'student_login', 'StudentAvailableExamsView', 'StudentExamQuestionsView',
    'submit_exam', 'get_exam_result', 'calculate_exam_result', 'get_student_scheduled_exams', 'get_student_schedule',
    
    # Authentication
    'login_view', 'refresh_token_view', 'verify_token_view',
    
    # Roles
    'get_all_roles', 'create_role', 'get_role_by_id', 'update_role', 'delete_role',
    
    # Users
    'get_all_users', 'create_user', 'get_user_by_id', 'update_user', 'delete_user', 'get_all_teachers',
    
    # Student Assignments
    'assign_students_bulk', 'assign_student_single', 'get_all_assignments', 
    'delete_assignment', 'delete_assignments_bulk', 'get_available_schedules',
    
    # Results Management
    'toggle_exam_publication', 'get_student_exam_result_enhanced',
    'get_all_results_by_teacher', 'get_published_exams',
    
    # Blocklist Question Management
    'block_question', 'get_all_blocked_questions', 'restore_blocked_question', 'delete_blocked_question', 'block_question_by_id',
    
    # Viva Rubrics Management
    'create_viva_rubrics', 'get_all_viva_rubrics', 'get_viva_rubrics_by_id',
    'get_viva_rubrics_by_department', 'update_viva_rubrics', 'delete_viva_rubrics',
    
    # Marks Distribution Management
    'create_marks_distribution', 'get_all_marks_distribution', 'get_marks_distribution_by_id',
    'get_marks_distribution_by_department', 'update_marks_distribution', 'delete_marks_distribution',

    # Viva Assignment Management
    'create_viva_assignment', 'get_all_viva_assignments', 'delete_viva_assignment',
    
    # Viva Marks Management
    'add_viva_marks', 'delete_viva_marks',
    'upload_docx_scrape_multipart',
    'insert_scrapped_questions'
]