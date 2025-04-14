from django.urls import path, include
from rest_framework_nested import routers
from .views import (
    CourseViewSet,
    CourseTeacherViewSet,
    CourseAssistantViewSet,
    CourseEnrollmentViewSet
)

router = routers.DefaultRouter()
router.register(r'', CourseViewSet, basename='course')
router.register(r'enrollments', CourseEnrollmentViewSet, basename='enrollment')

course_router = routers.NestedDefaultRouter(router, r'', lookup='course')
course_router.register(r'teachers', CourseTeacherViewSet, basename='course-teacher')
course_router.register(r'assistants', CourseAssistantViewSet, basename='course-assistant')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(course_router.urls)),
]
