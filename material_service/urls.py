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