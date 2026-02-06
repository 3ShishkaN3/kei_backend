from django.urls import include, path
from rest_framework_nested import routers
from .views import DictionarySectionViewSet, DictionaryEntryViewSet, KanjiRecognitionViewSet

router = routers.SimpleRouter()
router.register(r'', DictionarySectionViewSet, basename='dictsection')
router.register(r'kanji', KanjiRecognitionViewSet, basename='dict-kanji')

sections_router = routers.NestedSimpleRouter(router, r'', lookup='section')
sections_router.register(r'entries', DictionaryEntryViewSet, basename='section-entries')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(sections_router.urls)),
]
