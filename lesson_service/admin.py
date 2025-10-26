from django.contrib import admin
from .models import Lesson, Section, SectionCompletion, LessonCompletion

class SectionInline(admin.TabularInline):
    model = Section
    extra = 1 
    ordering = ('order',)

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'created_by', 'created_at', 'section_count_display')
    list_filter = ('course', 'created_at')
    search_fields = ('title', 'course__title')
    inlines = [SectionInline]

    def section_count_display(self, obj):
        return obj.sections.count()
    section_count_display.short_description = 'Кол-во разделов'

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'lesson', 'order', 'created_at')
    list_filter = ('lesson__course', 'lesson')
    search_fields = ('title', 'lesson__title')
    ordering = ('lesson', 'order')

@admin.register(SectionCompletion)
class SectionCompletionAdmin(admin.ModelAdmin):
    list_display = ('student', 'section', 'completed_at')
    list_filter = ('completed_at', 'section__lesson__course')
    search_fields = ('student__username', 'section__title', 'section__lesson__title')

@admin.register(LessonCompletion)
class LessonCompletionAdmin(admin.ModelAdmin):
    list_display = ('student', 'lesson', 'completed_at')
    list_filter = ('completed_at', 'lesson__course')
    search_fields = ('student__username', 'lesson__title')