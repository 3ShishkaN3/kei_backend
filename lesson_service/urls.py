from django.urls import include, path
from rest_framework_nested import routers
from .views import (
    LessonViewSet,
    SectionViewSet,
    SectionItemViewSet,
)
from dict_service.views import PrimaryLessonEntriesViewSet

router = routers.SimpleRouter()
router.register(r'', LessonViewSet, basename='lesson')

sections_router = routers.NestedSimpleRouter(router, r'', lookup='lesson')
sections_router.register(r'sections', SectionViewSet, basename='lesson-sections')

items_router = routers.NestedSimpleRouter(sections_router, r'sections', lookup='section')
items_router.register(r'items', SectionItemViewSet, basename='section-items')

primary_router = routers.NestedSimpleRouter(router, r'', lookup='lesson')
primary_router.register(
    r'primary_dictionary_entries',
    PrimaryLessonEntriesViewSet,
    basename='lesson-primary-entries'
)

urlpatterns = [
    path('', include(router.urls)),
    path('', include(sections_router.urls)),
    path('', include(items_router.urls)),     
    path('', include(primary_router.urls)), 
]