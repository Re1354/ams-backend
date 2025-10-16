from .role import Role
from .user import User
from .scrapped_question import ScrappedQuestion
from .exam import Exam
from .exam_question import ExamQuestion
from .exam_schedule import ExamSchedule
from .students import Students
from .submission import Submission
from .menu import Menu
from .role_menu import RoleMenu
from .departments import Department
from .subjects_demartments import SubjectDepartment
from .subjects import Subject
from .blocklist_question import BlocklistQuestion
from .student_assign_teacher_exam import StudentAssignTeacherExam
from .published_exam import PublishedExam
from .viva_rubrics import VivaRubrics
from .marks_distribution import MarksDistribution
from .viva_marks import VivaMarks
from .viva_assign import VivaAssignment



__all__ = [
    'Role',
    'User', 
    'ScrappedQuestion',
    'Exam',
    'ExamQuestion',
    'ExamSchedule',
    'Students',
    'Submission',
    'Menu',
    'RoleMenu',
    'Department',
    'SubjectDepartment',
    'Subject',
    'BlocklistQuestion',
    'StudentAssignTeacherExam',
    'PublishedExam',
    'VivaRubrics',
    'MarksDistribution',
    'VivaMarks',
    'VivaAssignment',

]