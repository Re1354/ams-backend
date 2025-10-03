# Import all views to make them available when importing from views
from .questions import AllScrappedQuestionsView, questions_stats, total_questions
from .exams import (
    CreateExamAPIView, AllExamsView, ExamQuestionListView, AddQuestionToExamView,
    ExamQuestionDetailView, DeleteExamView
)
from .students import AllStudentsView, StudentDetailView
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

# Make all views available when importing from mainapp.views
__all__ = [
    # Questions
    'AllScrappedQuestionsView', 'questions_stats', 'total_questions',
    
    # Exams
    'CreateExamAPIView', 'AllExamsView', 'ExamQuestionListView', 
    'AddQuestionToExamView', 'ExamQuestionDetailView', 'DeleteExamView',
    
    # Students
    'AllStudentsView', 'StudentDetailView',
    
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
    'delete_assignment', 'delete_assignments_bulk', 'get_available_schedules'
]