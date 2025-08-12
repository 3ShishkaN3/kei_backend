from rest_framework import serializers
from .models import UserProgress, CourseProgress, LessonProgress, TestProgress, LearningStats


class UserProgressSerializer(serializers.ModelSerializer):
    """Сериализатор для общего прогресса пользователя"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = UserProgress
        fields = [
            'id', 'username', 'email', 'total_courses_enrolled', 'total_courses_completed',
            'total_lessons_completed', 'total_sections_completed', 'total_tests_passed',
            'total_tests_failed', 'total_learning_time_minutes', 'last_activity',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


class CourseProgressSerializer(serializers.ModelSerializer):
    """Сериализатор для прогресса по курсу"""
    username = serializers.CharField(source='user.username', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_subtitle = serializers.CharField(source='course.subtitle', read_only=True)
    
    class Meta:
        model = CourseProgress
        fields = [
            'id', 'username', 'course_title', 'course_subtitle', 'total_lessons',
            'completed_lessons', 'total_sections', 'completed_sections', 'total_tests',
            'passed_tests', 'failed_tests', 'completion_percentage', 'started_at',
            'completed_at', 'last_activity', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class LessonProgressSerializer(serializers.ModelSerializer):
    """Сериализатор для прогресса по уроку"""
    username = serializers.CharField(source='user.username', read_only=True)
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    course_title = serializers.CharField(source='lesson.course.title', read_only=True)
    
    class Meta:
        model = LessonProgress
        fields = [
            'id', 'username', 'lesson_title', 'course_title', 'total_sections',
            'completed_sections', 'total_tests', 'passed_tests', 'failed_tests',
            'completion_percentage', 'started_at', 'completed_at', 'last_activity',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


class TestProgressSerializer(serializers.ModelSerializer):
    """Сериализатор для прогресса по тестам"""
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = TestProgress
        fields = [
            'id', 'username', 'test_id', 'test_title', 'test_type', 'section_id',
            'lesson_id', 'course_id', 'attempts_count', 'best_score', 'last_score',
            'status', 'first_attempt_at', 'last_attempt_at', 'completed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields


class LearningStatsSerializer(serializers.ModelSerializer):
    """Сериализатор для статистики обучения"""
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = LearningStats
        fields = [
            'id', 'username', 'total_study_days', 'current_streak_days',
            'longest_streak_days', 'average_daily_time_minutes', 'total_achievements',
            'level', 'experience_points', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class LeaderboardEntrySerializer(serializers.Serializer):
    """Сериализатор для записей рейтинга"""
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    completion_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    completed_lessons = serializers.IntegerField()
    completed_sections = serializers.IntegerField()
    passed_tests = serializers.IntegerField()
    total_learning_time_minutes = serializers.IntegerField()
    rank = serializers.IntegerField()


class ProgressSummarySerializer(serializers.Serializer):
    """Сериализатор для сводки прогресса"""
    total_courses = serializers.IntegerField()
    active_courses = serializers.IntegerField()
    completed_courses = serializers.IntegerField()
    total_lessons = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()
    total_sections = serializers.IntegerField()
    completed_sections = serializers.IntegerField()
    total_tests = serializers.IntegerField()
    passed_tests = serializers.IntegerField()
    failed_tests = serializers.IntegerField()
    overall_completion_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_learning_time_hours = serializers.DecimalField(max_digits=6, decimal_places=2)
    current_streak_days = serializers.IntegerField()
    level = serializers.IntegerField()
    experience_points = serializers.IntegerField()
