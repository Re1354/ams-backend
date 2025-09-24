from django.contrib import admin
from .models import ScrappedQuestion

# Register your models here.

@admin.register(ScrappedQuestion)
class ScrappedQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'questions_preview', 'type', 'marks', 'semester')
    list_filter = ('type', 'subject', 'semester', 'marks')
    search_fields = ('subject', 'questions', 'semester')
    list_per_page = 25
    
    def questions_preview(self, obj):
        return obj.questions[:100] + "..." if len(obj.questions) > 100 else obj.questions
    questions_preview.short_description = 'Questions Preview'
