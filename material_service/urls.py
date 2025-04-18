# material_service/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TextMaterialViewSet, ImageMaterialViewSet, AudioMaterialViewSet,
    VideoMaterialViewSet, DocumentMaterialViewSet, TestViewSet,
    TestSubmissionViewSet
)

router = DefaultRouter()
router.register(r'text', TextMaterialViewSet, basename='textmaterial')
router.register(r'image', ImageMaterialViewSet, basename='imagematerial')
router.register(r'audio', AudioMaterialViewSet, basename='audiomaterial')
router.register(r'video', VideoMaterialViewSet, basename='videomaterial')
router.register(r'document', DocumentMaterialViewSet, basename='documentmaterial')
router.register(r'tests', TestViewSet, basename='test')
router.register(r'submissions', TestSubmissionViewSet, basename='testsubmission')

urlpatterns = [
    path('', include(router.urls)),
]

# Примеры URL:
# GET /api/materials/text/ - Список текстов
# POST /api/materials/text/ - Создать текст
# GET /api/materials/tests/ - Список тестов
# POST /api/materials/tests/ - Создать тест (с вложенными компонентами)
# GET /api/materials/tests/{test_pk}/ - Детали теста
# POST /api/materials/tests/{test_pk}/submit/ - Отправить ответ на тест (студент)
# GET /api/materials/submissions/ - Список отправок (студент видит свои, персонал - все)
# GET /api/materials/submissions/{sub_pk}/ - Детали конкретной отправки