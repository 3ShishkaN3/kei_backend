from django.contrib import admin
from .models import UserKnowledgeProfile, DailyChallenge, ChallengeTest


class ChallengeTestInline(admin.TabularInline):
    model = ChallengeTest
    extra = 0
    readonly_fields = ('test', 'order')
    ordering = ('order',)


@admin.register(UserKnowledgeProfile)
class UserKnowledgeProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'last_analyzed_at', 'updated_at')
    list_filter = ('course',)
    search_fields = ('user__username',)
    readonly_fields = ('profile_data', 'created_at', 'updated_at')


@admin.register(DailyChallenge)
class DailyChallengeAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'course', 'date',
        'generation_status', 'completion_status',
        'correct_items', 'total_items', 'coins_awarded',
    )
    list_filter = ('generation_status', 'completion_status', 'date', 'course')
    search_fields = ('user__username',)
    readonly_fields = (
        'celery_task_id', 'blitz_quizzes', 'media_placeholders',
        'created_at', 'updated_at', 'completed_at',
    )
    inlines = [ChallengeTestInline]


@admin.register(ChallengeTest)
class ChallengeTestAdmin(admin.ModelAdmin):
    list_display = ('challenge', 'test', 'order')
    search_fields = ('challenge__user__username', 'test__title')
