from django.urls import include, path
from rest_framework_nested import routers
from .views import (
    CourseViewSet,
    CourseTeacherViewSet,
    CourseAssistantViewSet,
    CourseEnrollmentViewSet
)
from dict_service.views import DictionarySectionViewSet
from lesson_service.views import (
    LessonViewSet,
    SectionViewSet,
    SectionItemViewSet,
)
from dict_service.views import PrimaryLessonEntriesViewSet


router = routers.DefaultRouter()
router.register(r'', CourseViewSet, basename='course')
router.register(r'enrollments', CourseEnrollmentViewSet, basename='enrollment')

course_router = routers.NestedDefaultRouter(router, r'', lookup='course')
course_router.register(r'teachers', CourseTeacherViewSet, basename='course-teachers')
course_router.register(r'assistants', CourseAssistantViewSet, basename='course-assistants')
course_router.register(r'dictionary_sections', DictionarySectionViewSet, basename='course-dictsections')
course_router.register(r'lessons', LessonViewSet, basename='course-lessons')

lessons_router = routers.NestedDefaultRouter(course_router, r'lessons', lookup='lesson')
lessons_router.register(r'sections', SectionViewSet, basename='lesson-sections')

sections_router = routers.NestedDefaultRouter(lessons_router, r'sections', lookup='section')
sections_router.register(r'items', SectionItemViewSet, basename='section-items')

primary_router = routers.NestedDefaultRouter(course_router, r'lessons', lookup='lesson')
primary_router.register(
    r'primary_dictionary_entries',
    PrimaryLessonEntriesViewSet,
    basename='lesson-primary-entries'
)

urlpatterns = [
    path('', include(router.urls)),
    path('', include(course_router.urls)),
    path('', include(lessons_router.urls)),
    path('', include(sections_router.urls)),
    path('', include(primary_router.urls)),
]
