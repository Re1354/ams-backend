from django.contrib import admin
from .models import (
    Role,
    User,
    ScrappedQuestion,
    Exam,
    ExamQuestion,
    ExamSchedule,
    Students,
    Submission,
    Menu,
    RoleMenu,
    Department,
    SubjectDepartment,
    Subject,
    BlocklistQuestion,
    StudentAssignTeacherExam,
    PublishedExam,
    VivaRubrics,
    MarksDistribution,
    VivaMarks,
    VivaAssignment,
    DepartmentThreshold,
    AdmissionResult,
)

# Register your models here.

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('id', 'role_name')
    search_fields = ('role_name',)
    list_per_page = 25


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'email', 'role', 'department', 'created_at')
    list_filter = ('role', 'department', 'created_at')
    search_fields = ('username', 'email')
    list_per_page = 25
    raw_id_fields = ('role', 'department')


@admin.register(ScrappedQuestion)
class ScrappedQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'questions_preview', 'type', 'marks', 'semester')
    list_filter = ('type', 'subject', 'semester', 'marks')
    search_fields = ('subject', 'questions', 'semester')
    list_per_page = 25
    
    def questions_preview(self, obj):
        return obj.questions[:100] + "..." if len(obj.questions) > 100 else obj.questions
    questions_preview.short_description = 'Questions Preview'


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('id', 'department', 'semester', 'total_questions', 'present_question', 'total_marks', 'duration_minutes', 'faculty', 'language', 'created_at')
    list_filter = ('department', 'semester', 'language', 'faculty', 'created_at')
    search_fields = ('department', 'semester', 'faculty')
    list_per_page = 25


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'exam', 'question_text_preview', 'type', 'marks', 'subject')
    list_filter = ('type', 'marks', 'subject')
    search_fields = ('question_text', 'answer', 'subject')
    list_per_page = 25
    raw_id_fields = ('exam',)
    
    def question_text_preview(self, obj):
        return obj.question_text[:100] + "..." if len(obj.question_text) > 100 else obj.question_text
    question_text_preview.short_description = 'Question Text'


@admin.register(ExamSchedule)
class ExamScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'exam', 'start_time', 'end_time', 'is_active')
    list_filter = ('is_active', 'start_time', 'end_time')
    search_fields = ('exam__department', 'exam__semester')
    list_per_page = 25
    raw_id_fields = ('exam',)


@admin.register(Students)
class StudentsAdmin(admin.ModelAdmin):
    list_display = ('id', 'username', 'f_id', 'full_name', 'email', 'department_shortname', 'created_at')
    list_filter = ('department_shortname', 'created_at')
    search_fields = ('username', 'f_id', 'full_name', 'email')
    list_per_page = 25


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'exam', 'question', 'is_correct', 'submitted_at')
    list_filter = ('submitted_at', 'is_correct')
    search_fields = ('student__username', 'exam__department')
    list_per_page = 25
    raw_id_fields = ('student', 'exam', 'question')


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'component', 'link', 'icon')
    search_fields = ('label', 'component', 'link')
    list_per_page = 25


@admin.register(RoleMenu)
class RoleMenuAdmin(admin.ModelAdmin):
    list_display = ('id', 'role', 'menu')
    list_filter = ('role', 'menu')
    search_fields = ('role__role_name', 'menu__label')
    list_per_page = 25
    raw_id_fields = ('role', 'menu')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'department_name', 'department_shortname')
    search_fields = ('department_name', 'department_shortname')
    list_per_page = 25


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject_name')
    search_fields = ('subject_name',)
    list_per_page = 25


@admin.register(SubjectDepartment)
class SubjectDepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'department', 'subject_ids')
    list_filter = ('department',)
    search_fields = ('department__department_name',)
    list_per_page = 25
    raw_id_fields = ('department',)


@admin.register(BlocklistQuestion)
class BlocklistQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question_text_preview', 'type', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('question_text', 'answer')
    list_per_page = 25
    
    def question_text_preview(self, obj):
        return obj.question_text[:100] + "..." if len(obj.question_text) > 100 else obj.question_text
    question_text_preview.short_description = 'Question Text'


@admin.register(StudentAssignTeacherExam)
class StudentAssignTeacherExamAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'teacher', 'exam', 'schedule', 'created_at')
    list_filter = ('created_at', 'teacher', 'exam')
    search_fields = ('student__username', 'teacher__username', 'exam__department')
    list_per_page = 25
    raw_id_fields = ('student', 'teacher', 'exam', 'schedule')


@admin.register(PublishedExam)
class PublishedExamAdmin(admin.ModelAdmin):
    list_display = ('id', 'exam', 'is_published', 'published_at', 'created_at')
    list_filter = ('is_published', 'published_at', 'created_at')
    search_fields = ('exam__department', 'exam__semester')
    list_per_page = 25
    raw_id_fields = ('exam',)


@admin.register(VivaRubrics)
class VivaRubricsAdmin(admin.ModelAdmin):
    list_display = ('id', 'department', 'rubrics_preview', 'marks')
    list_filter = ('department',)
    search_fields = ('rubrics', 'department__department_name')
    list_per_page = 25
    raw_id_fields = ('department',)
    
    def rubrics_preview(self, obj):
        return obj.rubrics[:100] + "..." if obj.rubrics and len(obj.rubrics) > 100 else obj.rubrics
    rubrics_preview.short_description = 'Rubrics'


@admin.register(MarksDistribution)
class MarksDistributionAdmin(admin.ModelAdmin):
    list_display = ('id', 'department', 'ssc', 'hsc', 'diploma', 'main_marks', 'viva_marks')
    list_filter = ('department',)
    search_fields = ('department__department_name',)
    list_per_page = 25
    raw_id_fields = ('department',)


@admin.register(VivaMarks)
class VivaMarksAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'marks', 'remarks_preview')
    search_fields = ('student__username', 'remarks')
    list_per_page = 25
    raw_id_fields = ('student',)
    
    def remarks_preview(self, obj):
        return obj.remarks[:100] + "..." if obj.remarks and len(obj.remarks) > 100 else obj.remarks
    remarks_preview.short_description = 'Remarks'



@admin.register(VivaAssignment)
class VivaAssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'teacher', 'exam', 'time', 'room', 'created_at')
    list_filter = ('created_at', 'teacher', 'room')
    search_fields = ('student__username', 'teacher__username', 'exam__department', 'room')
    list_per_page = 25
    raw_id_fields = ('student', 'teacher', 'exam')


@admin.register(DepartmentThreshold)
class DepartmentThresholdAdmin(admin.ModelAdmin):
    list_display = ('id', 'exam', 'department', 'min_threshold_mark', 'created_at', 'updated_at')
    list_filter = ('department', 'created_at', 'updated_at')
    search_fields = ('exam__department', 'department__department_name')
    list_per_page = 25
    raw_id_fields = ('exam', 'department')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AdmissionResult)
class AdmissionResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'student', 'exam', 'department', 'total_marks', 
        'is_selected', 'status', 'created_at'
    )
    list_filter = ('is_selected', 'status', 'department', 'created_at')
    search_fields = (
        'student__username', 'student__f_id', 'student__full_name',
        'exam__department', 'department__department_name'
    )
    list_per_page = 25
    raw_id_fields = ('exam', 'student', 'department')
    readonly_fields = ('total_marks', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('exam', 'student', 'department', 'status')
        }),
        ('Marks Details', {
            'fields': ('mcq_marks', 'viva_marks', 'total_marks', 'subject_wise_marks')
        }),
        ('Selection', {
            'fields': ('is_selected', 'threshold_applied', 'remarks')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
