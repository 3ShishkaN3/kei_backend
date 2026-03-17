from django.contrib import admin
from .models import Exam, ExamSection, ExamSectionItem, ExamAttempt, ExamAnswer


class ExamSectionItemInline(admin.TabularInline):
    model = ExamSectionItem
    extra = 1
    raw_id_fields = ['test']


class ExamSectionInline(admin.TabularInline):
    model = ExamSection
    extra = 1
    show_change_link = True


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'duration_minutes', 'is_published', 'created_at']
    list_filter = ['is_published', 'course']
    search_fields = ['title', 'course__title']
    inlines = [ExamSectionInline]


@admin.register(ExamSection)
class ExamSectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'exam', 'order']
    list_filter = ['exam']
    inlines = [ExamSectionItemInline]


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'status', 'total_score', 'started_at', 'finished_at']
    list_filter = ['status', 'exam']
    search_fields = ['student__username', 'exam__title']
    readonly_fields = ['started_at', 'finished_at']


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'exam_section_item', 'score', 'is_correct', 'submitted_at']
    list_filter = ['is_correct']
