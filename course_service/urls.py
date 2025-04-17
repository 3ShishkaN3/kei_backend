# course_service/urls.py
from django.urls import path, include
from rest_framework_nested import routers
from .views import (
    CourseViewSet,
    CourseTeacherViewSet,
    CourseAssistantViewSet,
    CourseEnrollmentViewSet
)
# Импортируем ViewSet урока из lesson_service
from lesson_service.views import LessonViewSet, SectionViewSet

router = routers.DefaultRouter()
router.register(r'', CourseViewSet, basename='') 
router.register(r'enrollments', CourseEnrollmentViewSet, basename='enrollment')

course_router = routers.NestedDefaultRouter(router, r'', lookup='course')
course_router.register(r'teachers', CourseTeacherViewSet, basename='course-teacher')
course_router.register(r'assistants', CourseAssistantViewSet, basename='course-assistant')


course_router.register(r'lessons', LessonViewSet, basename='course-lessons')


lessons_router = routers.NestedDefaultRouter(course_router, r'lessons', lookup='lesson')
lessons_router.register(r'sections', SectionViewSet, basename='lesson-sections')
# ========================================================

urlpatterns = [
    path('', include(router.urls)),
    path('', include(course_router.urls)),
    path('', include(lessons_router.urls)),
]