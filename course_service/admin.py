from django.contrib import admin
from .models import Course, CourseTeacher, CourseAssistant, CourseEnrollment

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('title', 'description', 'created_by__username')
    date_hierarchy = 'created_at'


@admin.register(CourseTeacher)
class CourseTeacherAdmin(admin.ModelAdmin):
    list_display = ('course', 'teacher', 'is_primary', 'added_at')
    list_filter = ('is_primary', 'added_at')
    search_fields = ('course__title', 'teacher__username')


@admin.register(CourseAssistant)
class CourseAssistantAdmin(admin.ModelAdmin):
    list_display = ('course', 'assistant', 'added_at')
    list_filter = ('added_at',)
    search_fields = ('course__title', 'assistant__username')


@admin.register(CourseEnrollment)
class CourseEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'status', 'enrolled_at', 'completed_at')
    list_filter = ('status', 'enrolled_at', 'completed_at')
    search_fields = ('course__title', 'student__username')
    date_hierarchy = 'enrolled_at'