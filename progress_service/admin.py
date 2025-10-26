from django.contrib import admin
from .models import UserProgress, CourseProgress, LessonProgress, SectionProgress, TestProgress, LearningStats


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_courses_enrolled', 'total_courses_completed', 
                   'total_lessons_completed', 'total_sections_completed', 
                   'total_tests_passed', 'total_tests_failed', 'last_activity']
    list_filter = ['last_activity', 'created_at', 'updated_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-last_activity']


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'course', 'completion_percentage', 'completed_lessons', 
                   'completed_sections', 'passed_tests', 'failed_tests', 'last_activity']
    list_filter = ['completion_percentage', 'started_at', 'completed_at', 'last_activity']
    search_fields = ['user__username', 'course__title', 'course__subtitle']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-last_activity']


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'lesson', 'completion_percentage', 'completed_sections', 
                   'passed_tests', 'failed_tests', 'last_activity']
    list_filter = ['completion_percentage', 'started_at', 'completed_at', 'last_activity']
    search_fields = ['user__username', 'lesson__title', 'lesson__course__title']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-last_activity']


@admin.register(SectionProgress)
class SectionProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'section', 'completion_percentage', 'is_visited', 
                   'total_items', 'completed_items', 'total_tests', 'passed_tests', 'last_activity']
    list_filter = ['completion_percentage', 'is_visited', 'started_at', 'completed_at', 'last_activity']
    search_fields = ['user__username', 'section__title', 'section__lesson__title']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-last_activity']


@admin.register(TestProgress)
class TestProgressAdmin(admin.ModelAdmin):
    list_display = ['user', 'test_title', 'test_type', 'status', 'attempts_count', 
                   'best_score', 'last_score', 'last_attempt_at']
    list_filter = ['test_type', 'status', 'first_attempt_at', 'last_attempt_at', 'completed_at']
    search_fields = ['user__username', 'test_title']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-last_attempt_at']


@admin.register(LearningStats)
class LearningStatsAdmin(admin.ModelAdmin):
    list_display = ['user', 'level', 'experience_points', 'total_study_days', 
                   'current_streak_days', 'longest_streak_days', 'total_achievements']
    list_filter = ['level', 'total_study_days', 'current_streak_days', 'longest_streak_days']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-level', '-experience_points']
