# Authentication and User Management
from .auth import (
    RoleSerializer,
    UserSerializer,
    LoginSerializer,
    UserDetailSerializer
)

# Department Management
from .departments import (
    DepartmentSerializer,
    DepartmentCreateSerializer,
    DepartmentDetailSerializer
)

# Faculty Management
from .faculty import (
    FacultySerializer,
    FacultyCreateSerializer
)

# Faculty Department Mapping
from .faculty_department import (
    FacultyDepartmentSerializer,
    FacultyDepartmentCreateSerializer
)

# Menu Management
from .menu import (
    MenuSerializer,
    RoleMenuSerializer,
    RoleMenuCreateSerializer
)

# Question Management
from .question import (
    ScrappedQuestionSerializer,
    TotalQuestionsSerializer,
    BulkDeleteScrappedQuestionsSerializer,
)

# Exam Management
from .exam import (
    ExamCreateSerializer,
    ExamSerializer,
    ExamQuestionSerializer,
    ExamScheduleSerializer,
    ExamScheduleCreateSerializer,
    CreateExamScheduleSerializer,
    ExamResultSerializer
)

# Student Management
from .student import (
    StudentsSerializer,
    SubmissionSerializer
)

# Subject Management
from .subject import (
    SubjectSerializer,
    SubjectDepartmentSerializer,
    SubjectDepartmentCreateSerializer
)

# Exam Generation
from .exam_generation import (
    ExamGenerationRequestSerializer,
    ExamSaveRequestSerializer,
    GeneratedExamResponseSerializer,
    ExamGenerationBlocklistSerializer,
    BlockQuestionRequestSerializer,
    UnblockQuestionRequestSerializer
)

# Student App
from .student_app import (
    StudentLoginSerializer,
    ExamSubmissionSerializer,
    StudentLoginResponseSerializer,
    ExamSubmissionResponseSerializer
)

# API Info
from .api_info import (
    APIInfoResponseSerializer
)

# Viva Rubrics
from .viva_rubrics import (
    VivaRubricsSerializer,
    VivaRubricsCreateSerializer,
    VivaRubricsUpdateSerializer
)

# Marks Distribution
from .marks_distribution import (
    MarksDistributionSerializer,
    MarksDistributionCreateSerializer,
    MarksDistributionUpdateSerializer
)

__all__ = [
    # Auth
    'RoleSerializer',
    'UserSerializer',
    'LoginSerializer',
    'UserDetailSerializer',
    
    # Department
    'DepartmentSerializer',
    'DepartmentCreateSerializer',
    'DepartmentDetailSerializer',
    
    # Faculty
    'FacultySerializer',
    'FacultyCreateSerializer',
    
    # Faculty Department Mapping
    'FacultyDepartmentSerializer',
    'FacultyDepartmentCreateSerializer',
    
    # Menu
    'MenuSerializer',
    'RoleMenuSerializer', 
    'RoleMenuCreateSerializer',
    
    # Question
    'ScrappedQuestionSerializer',
    'TotalQuestionsSerializer',
    'BulkDeleteScrappedQuestionsSerializer',
    
    # Exam
    'ExamCreateSerializer',
    'ExamSerializer',
    'ExamQuestionSerializer',
    'ExamScheduleSerializer',
    'ExamScheduleCreateSerializer',
    'CreateExamScheduleSerializer',
    'ExamResultSerializer',
    
    # Student
    'StudentsSerializer',
    'SubmissionSerializer',
    
    # Subject
    'SubjectSerializer',
    'SubjectDepartmentSerializer',
    'SubjectDepartmentCreateSerializer',
    
    # Exam Generation
    'ExamGenerationRequestSerializer',
    'ExamSaveRequestSerializer',
    'GeneratedExamResponseSerializer',
    'BlocklistQuestionSerializer',
    'BlockQuestionRequestSerializer',
    'UnblockQuestionRequestSerializer',
    
    # Student App
    'StudentLoginSerializer',
    'ExamSubmissionSerializer',
    'StudentLoginResponseSerializer',
    'ExamSubmissionResponseSerializer',
    
    # API Info
    'APIInfoResponseSerializer',
    
    # Viva Rubrics
    'VivaRubricsSerializer',
    'VivaRubricsCreateSerializer',
    'VivaRubricsUpdateSerializer',
    
    # Marks Distribution
    'MarksDistributionSerializer',
    'MarksDistributionCreateSerializer',
    'MarksDistributionUpdateSerializer'
]
