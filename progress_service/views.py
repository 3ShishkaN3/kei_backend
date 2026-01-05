from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg, Sum, F
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from .models import UserProgress, CourseProgress, LessonProgress, SectionProgress, TestProgress, LearningStats
from auth_service.models import User
from auth_service.serializers import UserSerializer
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
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            return UserProgress.objects.filter(
                course_progress__course_id__in=managed_courses
            ).distinct()
        else:
            return UserProgress.objects.filter(user=user)

    @action(detail=True, methods=['get'])
    def summary(self, request, pk=None):
        """Получить сводку прогресса пользователя"""
        progress = self.get_object()
        
        learning_stats, _ = LearningStats.objects.get_or_create(user=progress.user)
        
        total_courses = progress.total_courses_enrolled
        completed_courses = progress.total_courses_completed
        overall_completion_percentage = (completed_courses / total_courses * 100) if total_courses > 0 else 0
        
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
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = CourseProgress.objects.filter(course_id__in=managed_courses)
        else:
            queryset = CourseProgress.objects.filter(user=user)
        
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        completion_status = self.request.query_params.get('completion_status')
        if completion_status == 'completed':
            queryset = queryset.filter(completion_percentage=100)
        elif completion_status == 'in_progress':
            queryset = queryset.filter(completion_percentage__gt=0, completion_percentage__lt=100)
        elif completion_status == 'not_started':
            queryset = queryset.filter(completion_percentage=0)

        
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
        
        course = get_object_or_404(Course, pk=course_id)
        user = request.user
        
        if user.role not in ['admin', 'teacher', 'assistant']:
            if not course.enrollments.filter(student=user, status='active').exists():
                return Response(
                    {"error": "Нет доступа к рейтингу этого курса"},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif user.role in ['teacher', 'assistant']:
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
        
        leaderboard = CourseProgress.objects.filter(
            course_id=course_id
        ).select_related('user').order_by(
            '-completion_percentage',
            '-completed_lessons',
            '-completed_sections',
            '-passed_tests'
        )[:50]
        
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
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = LessonProgress.objects.filter(lesson__course_id__in=managed_courses)
        else:
            queryset = LessonProgress.objects.filter(user=user)
        
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(lesson__course_id=course_id)
        
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
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = SectionProgress.objects.filter(section__lesson__course_id__in=managed_courses)
        else:
            queryset = SectionProgress.objects.filter(user=user)
        
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(section__lesson__course_id=course_id)
        
        lesson_id = self.request.query_params.get('lesson_id')
        if lesson_id:
            queryset = queryset.filter(section__lesson_id=lesson_id)
        
        section_id = self.request.query_params.get('section_id')
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        
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
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            queryset = TestProgress.objects.filter(course_id__in=managed_courses)
        else:
            queryset = TestProgress.objects.filter(user=user)
        
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        lesson_id = self.request.query_params.get('lesson_id')
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)
        
        test_type = self.request.query_params.get('test_type')
        if test_type:
            queryset = queryset.filter(test_type=test_type)
        
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
            if user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
            
            return LearningStats.objects.filter(
                user__course_progress__course_id__in=managed_courses
            ).distinct()
        else:
            return LearningStats.objects.filter(user=user)
    
    @action(detail=False, methods=['get'])
    def student_full_summary(self, request):
        """
        Получение полной сводки по ученику.
        
        Параметры:
        - user_id: ID ученика (обязательно)
        
        Возвращает полную информацию о прогрессе ученика по всем курсам.
        """
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response(
                {"error": "user_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.user.role == 'admin':
            pass
        elif request.user.role in ['teacher', 'assistant']:
            if request.user.role == 'teacher':
                managed_courses = CourseTeacher.objects.filter(teacher=request.user).values_list('course_id', flat=True)
            else:
                managed_courses = CourseAssistant.objects.filter(assistant=request.user).values_list('course_id', flat=True)
            
            has_access = CourseProgress.objects.filter(
                user=target_user,
                course_id__in=managed_courses
            ).exists()
            
            if not has_access and target_user != request.user:
                return Response(
                    {"error": "Нет доступа к прогрессу этого ученика"},
                    status=status.HTTP_403_FORBIDDEN
                )
        else:
            if target_user != request.user:
                return Response(
                    {"error": "Нет доступа"},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        user_progress, _ = UserProgress.objects.get_or_create(user=target_user)
        learning_stats, _ = LearningStats.objects.get_or_create(user=target_user)
        
        course_progress_list = CourseProgress.objects.filter(user=target_user)
        lesson_progress_list = LessonProgress.objects.filter(user=target_user)
        section_progress_list = SectionProgress.objects.filter(user=target_user)
        test_progress_list = TestProgress.objects.filter(user=target_user)
        
        from auth_service.serializers import UserSerializer
        summary = {
            "user": UserSerializer(target_user).data,
            "overall_progress": UserProgressSerializer(user_progress).data,
            "learning_stats": LearningStatsSerializer(learning_stats).data,
            "course_progress": CourseProgressSerializer(course_progress_list, many=True).data,
            "lesson_progress": LessonProgressSerializer(lesson_progress_list, many=True).data,
            "section_progress": SectionProgressSerializer(section_progress_list, many=True).data,
            "test_progress": TestProgressSerializer(test_progress_list, many=True).data,
        }
        
        return Response(summary, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'])
    def reset_progress(self, request):
        """
        Сброс прогресса ученика (только для администраторов).
        
        Параметры в теле запроса:
        - user_id: ID ученика (обязательно)
        - scope: область сброса - 'all', 'course', 'lesson', 'test' (по умолчанию 'all')
        - course_id: ID курса (если scope='course')
        - lesson_id: ID урока (если scope='lesson')
        - test_id: ID теста (если scope='test')
        """
        if request.user.role != 'admin':
            return Response(
                {"error": "Только администраторы могут сбрасывать прогресс"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_id = request.data.get('user_id')
        scope = request.data.get('scope', 'all')
        
        if not user_id:
            return Response(
                {"error": "user_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if scope == 'all':
            CourseProgress.objects.filter(user=target_user).delete()
            LessonProgress.objects.filter(user=target_user).delete()
            SectionProgress.objects.filter(user=target_user).delete()
            TestProgress.objects.filter(user=target_user).delete()
            
            user_progress, _ = UserProgress.objects.get_or_create(user=target_user)
            user_progress.total_courses_enrolled = 0
            user_progress.total_courses_completed = 0
            user_progress.total_lessons_completed = 0
            user_progress.total_sections_completed = 0
            user_progress.total_tests_passed = 0
            user_progress.total_tests_failed = 0
            user_progress.total_learning_time_minutes = 0
            user_progress.save()
            
            return Response({
                "message": "Весь прогресс ученика сброшен",
                "user_id": user_id
            }, status=status.HTTP_200_OK)
        
        elif scope == 'course':
            course_id = request.data.get('course_id')
            if not course_id:
                return Response(
                    {"error": "course_id обязателен для scope='course'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            CourseProgress.objects.filter(user=target_user, course_id=course_id).delete()
            LessonProgress.objects.filter(user=target_user, lesson__course_id=course_id).delete()
            SectionProgress.objects.filter(user=target_user, section__lesson__course_id=course_id).delete()
            TestProgress.objects.filter(user=target_user, course_id=course_id).delete()
            
            return Response({
                "message": f"Прогресс по курсу {course_id} сброшен",
                "user_id": user_id,
                "course_id": course_id
            }, status=status.HTTP_200_OK)
        
        elif scope == 'lesson':
            lesson_id = request.data.get('lesson_id')
            if not lesson_id:
                return Response(
                    {"error": "lesson_id обязателен для scope='lesson'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            LessonProgress.objects.filter(user=target_user, lesson_id=lesson_id).delete()
            SectionProgress.objects.filter(user=target_user, section__lesson_id=lesson_id).delete()
            TestProgress.objects.filter(user=target_user, lesson_id=lesson_id).delete()
            
            return Response({
                "message": f"Прогресс по уроку {lesson_id} сброшен",
                "user_id": user_id,
                "lesson_id": lesson_id
            }, status=status.HTTP_200_OK)
        
        elif scope == 'test':
            test_id = request.data.get('test_id')
            if not test_id:
                return Response(
                    {"error": "test_id обязателен для scope='test'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            TestProgress.objects.filter(user=target_user, test_id=test_id).delete()
            
            return Response({
                "message": f"Прогресс по тесту {test_id} сброшен",
                "user_id": user_id,
                "test_id": test_id
            }, status=status.HTTP_200_OK)
        
        return Response(
            {"error": "Неизвестный scope. Используйте: 'all', 'course', 'lesson', 'test'"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=False, methods=['post'])
    def correct_test_score(self, request):
        """
        Ручная коррекция результатов теста (только для администраторов).
        
        Параметры в теле запроса:
        - user_id: ID ученика (обязательно)
        - test_id: ID теста (обязательно)
        - score: новый балл (0-100) (обязательно)
        - status: новый статус ('passed', 'failed', 'in_progress') (опционально)
        """
        if request.user.role != 'admin':
            return Response(
                {"error": "Только администраторы могут корректировать результаты тестов"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_id = request.data.get('user_id')
        test_id = request.data.get('test_id')
        score = request.data.get('score')
        new_status = request.data.get('status')
        
        if not all([user_id, test_id, score is not None]):
            return Response(
                {"error": "user_id, test_id и score обязательны"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            score = float(score)
            if score < 0 or score > 100:
                return Response(
                    {"error": "score должен быть в диапазоне 0-100"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response(
                {"error": "score должен быть числом"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Пользователь не найден"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        test_progress, created = TestProgress.objects.get_or_create(
            user=target_user,
            test_id=test_id,
            defaults={
                'best_score': score,
                'last_score': score,
                'attempts_count': 1,
                'status': 'passed' if score >= 50 else 'failed'
            }
        )
        
        if not created:
            test_progress.last_score = score
            if score > test_progress.best_score:
                test_progress.best_score = score
            test_progress.attempts_count += 1
            
            if new_status:
                if new_status in ['passed', 'failed', 'in_progress']:
                    test_progress.status = new_status
                else:
                    test_progress.status = 'passed' if score >= 50 else 'failed'
            else:
                test_progress.status = 'passed' if score >= 50 else 'failed'
            
            test_progress.save()
        
        serializer = TestProgressSerializer(test_progress)
        return Response({
            "message": "Результат теста успешно скорректирован",
            "test_progress": serializer.data
        }, status=status.HTTP_200_OK)