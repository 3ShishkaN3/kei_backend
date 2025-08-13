from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, Sum, F
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from .models import UserProgress, CourseProgress, LessonProgress, SectionProgress, TestProgress, LearningStats
from .serializers import (
    UserProgressSerializer, CourseProgressSerializer, LessonProgressSerializer,
    SectionProgressSerializer, TestProgressSerializer, LearningStatsSerializer, 
    LeaderboardEntrySerializer, ProgressSummarySerializer
)
from .permissions import CanViewOwnProgress, CanViewStudentProgress, CanViewCourseProgress, CanViewLeaderboard
from course_service.models import Course, CourseTeacher, CourseAssistant
from lesson_service.models import Lesson


class ProgressPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class UserProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для общего прогресса пользователя"""
    serializer_class = UserProgressSerializer
    permission_classes = [IsAuthenticated, CanViewOwnProgress]
    pagination_class = ProgressPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['total_courses_completed', 'total_lessons_completed', 'last_activity']
    ordering = ['-last_activity']

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return UserProgress.objects.all()
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники видят прогресс своих студентов
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            return UserProgress.objects.filter(
                course_progress__course_id__in=managed_courses
            ).distinct()
        else:
            # Студенты видят только свой прогресс
            return UserProgress.objects.filter(user=user)

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Получить сводку прогресса пользователя"""
        progress = self.get_object()
        
        # Получаем статистику обучения
        learning_stats, _ = LearningStats.objects.get_or_create(user=progress.user)
        
        # Рассчитываем общий процент завершения
        total_courses = progress.total_courses_enrolled
        completed_courses = progress.total_courses_completed
        overall_completion_percentage = (completed_courses / total_courses * 100) if total_courses > 0 else 0
        
        # Рассчитываем время обучения в часах
        total_learning_time_hours = progress.total_learning_time_minutes / 60
        
        summary_data = {
            'total_courses': total_courses,
            'active_courses': total_courses - completed_courses,
            'completed_courses': completed_courses,
            'total_lessons': progress.total_lessons_completed,
            'completed_lessons': progress.total_lessons_completed,
            'total_sections': progress.total_sections_completed,
            'completed_sections': progress.total_sections_completed,
            'total_tests': progress.total_tests_passed + progress.total_tests_failed,
            'passed_tests': progress.total_tests_passed,
            'failed_tests': progress.total_tests_failed,
            'overall_completion_percentage': round(overall_completion_percentage, 2),
            'total_learning_time_hours': round(total_learning_time_hours, 2),
            'current_streak_days': learning_stats.current_streak_days,
            'level': learning_stats.level,
            'experience_points': learning_stats.experience_points,
        }
        
        serializer = ProgressSummarySerializer(summary_data)
        return Response(serializer.data)


class CourseProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для прогресса по курсам"""
    serializer_class = CourseProgressSerializer
    permission_classes = [IsAuthenticated, CanViewCourseProgress]
    pagination_class = ProgressPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ['completion_percentage', 'started_at', 'completed_at', 'last_activity']
    ordering = ['-last_activity']
    search_fields = ['course__title', 'course__subtitle']

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            queryset = CourseProgress.objects.all()
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники видят прогресс по своим курсам
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = CourseProgress.objects.filter(course_id__in=managed_courses)
        else:
            # Студенты видят только свой прогресс
            queryset = CourseProgress.objects.filter(user=user)
        
        # Фильтрация по курсу
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        # Фильтрация по статусу завершения
        completion_status = self.request.query_params.get('completion_status')
        if completion_status == 'completed':
            queryset = queryset.filter(completion_percentage=100)
        elif completion_status == 'in_progress':
            queryset = queryset.filter(completion_percentage__lt=100)
        
        return queryset

    @action(detail=False, methods=['get'])
    def leaderboard(self, request):
        """Получить рейтинг по курсу"""
        course_id = request.query_params.get('course_id')
        if not course_id:
            return Response(
                {"error": "course_id обязателен для получения рейтинга"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Проверяем права доступа к курсу
        course = get_object_or_404(Course, pk=course_id)
        user = request.user
        
        if user.role not in ['admin', 'teacher', 'assistant']:
            # Студенты могут видеть рейтинг только по курсам, на которые они записаны
            if not course.enrollments.filter(student=user, status='active').exists():
                return Response(
                    {"error": "Нет доступа к рейтингу этого курса"},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники могут видеть рейтинг только по своим курсам
            if user.role == 'teacher':
                if not CourseTeacher.objects.filter(teacher=user, course=course).exists():
                    return Response(
                        {"error": "Нет доступа к рейтингу этого курса"},
                        status=status.HTTP_403_FORBIDDEN
                    )
            else:
                if not CourseAssistant.objects.filter(assistant=user, course=course).exists():
                    return Response(
                        {"error": "Нет доступа к рейтингу этого курса"},
                        status=status.HTTP_403_FORBIDDEN
                    )
        
        # Получаем рейтинг
        leaderboard = CourseProgress.objects.filter(
            course_id=course_id
        ).select_related('user').order_by(
            '-completion_percentage',
            '-completed_lessons',
            '-completed_sections',
            '-passed_tests'
        )[:50]  # Топ-50
        
        leaderboard_data = []
        for rank, progress in enumerate(leaderboard, 1):
            leaderboard_data.append({
                'user_id': progress.user.id,
                'username': progress.user.username,
                'completion_percentage': progress.completion_percentage,
                'completed_lessons': progress.completed_lessons,
                'completed_sections': progress.completed_sections,
                'passed_tests': progress.passed_tests,
                'total_learning_time_minutes': progress.user.progress.total_learning_time_minutes,
                'rank': rank
            })
        
        serializer = LeaderboardEntrySerializer(leaderboard_data, many=True)
        return Response(serializer.data)


class LessonProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для прогресса по урокам"""
    serializer_class = LessonProgressSerializer
    permission_classes = [IsAuthenticated, CanViewCourseProgress]
    pagination_class = ProgressPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['completion_percentage', 'started_at', 'completed_at', 'last_activity']
    ordering = ['-last_activity']

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            queryset = LessonProgress.objects.all()
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники видят прогресс по своим курсам
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = LessonProgress.objects.filter(lesson__course_id__in=managed_courses)
        else:
            # Студенты видят только свой прогресс
            queryset = LessonProgress.objects.filter(user=user)
        
        # Фильтрация по курсу
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(lesson__course_id=course_id)
        
        # Фильтрация по уроку
        lesson_id = self.request.query_params.get('lesson_id')
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)
        
        return queryset


class SectionProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для прогресса по секциям"""
    serializer_class = SectionProgressSerializer
    permission_classes = [IsAuthenticated, CanViewCourseProgress]
    pagination_class = ProgressPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['completion_percentage', 'started_at', 'completed_at', 'last_activity', 'visited_at']
    ordering = ['-last_activity']

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            queryset = SectionProgress.objects.all()
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники видят прогресс по своим курсам
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = SectionProgress.objects.filter(section__lesson__course_id__in=managed_courses)
        else:
            # Студенты видят только свой прогресс
            queryset = SectionProgress.objects.filter(user=user)
        
        # Фильтрация по курсу
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(section__lesson__course_id=course_id)
        
        # Фильтрация по уроку
        lesson_id = self.request.query_params.get('lesson_id')
        if lesson_id:
            queryset = queryset.filter(section__lesson_id=lesson_id)
        
        # Фильтрация по секции
        section_id = self.request.query_params.get('section_id')
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        
        # Фильтрация по статусу посещения
        visited = self.request.query_params.get('visited')
        if visited is not None:
            visited_bool = visited.lower() == 'true'
            queryset = queryset.filter(is_visited=visited_bool)
        
        return queryset


class TestProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для прогресса по тестам"""
    serializer_class = TestProgressSerializer
    permission_classes = [IsAuthenticated, CanViewCourseProgress]
    pagination_class = ProgressPagination
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ['best_score', 'last_score', 'attempts_count', 'last_attempt_at']
    ordering = ['-last_attempt_at']
    search_fields = ['test_title']

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            queryset = TestProgress.objects.all()
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники видят прогресс по своим курсам
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = TestProgress.objects.filter(course_id__in=managed_courses)
        else:
            # Студенты видят только свой прогресс
            queryset = TestProgress.objects.filter(user=user)
        
        # Фильтрация по курсу
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        # Фильтрация по уроку
        lesson_id = self.request.query_params.get('lesson_id')
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)
        
        # Фильтрация по типу теста
        test_type = self.request.query_params.get('test_type')
        if test_type:
            queryset = queryset.filter(test_type=test_type)
        
        # Фильтрация по статусу
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset


class LearningStatsViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для статистики обучения"""
    serializer_class = LearningStatsSerializer
    permission_classes = [IsAuthenticated, CanViewOwnProgress]
    pagination_class = ProgressPagination
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['level', 'experience_points', 'current_streak_days', 'total_study_days']
    ordering = ['-level', '-experience_points']

    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return LearningStats.objects.all()
        elif user.role in ['teacher', 'assistant']:
            # Преподаватели и помощники видят статистику своих студентов
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            return LearningStats.objects.filter(
                user__course_progress__course_id__in=managed_courses
            ).distinct()
        else:
            # Студенты видят только свою статистику
            return LearningStats.objects.filter(user=user)
