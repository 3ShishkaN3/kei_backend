from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserProgressViewSet, CourseProgressViewSet, LessonProgressViewSet,
    SectionProgressViewSet, TestProgressViewSet, LearningStatsViewSet
)

router = DefaultRouter()
router.register(r'users', UserProgressViewSet, basename='user-progress')
router.register(r'courses', CourseProgressViewSet, basename='course-progress')
router.register(r'lessons', LessonProgressViewSet, basename='lesson-progress')
router.register(r'sections', SectionProgressViewSet, basename='section-progress')
router.register(r'tests', TestProgressViewSet, basename='test-progress')
router.register(r'stats', LearningStatsViewSet, basename='learning-stats')

urlpatterns = [
    path('', include(router.urls)),
]
