from django.urls import include, path
from rest_framework_nested import routers
from .views import DictionarySectionViewSet, DictionaryEntryViewSet

router = routers.SimpleRouter()
router.register(r'', DictionarySectionViewSet, basename='dictsection')

sections_router = routers.NestedSimpleRouter(router, r'', lookup='section')
sections_router.register(r'entries', DictionaryEntryViewSet, basename='section-entries')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(sections_router.urls)),
]
