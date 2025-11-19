from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AchievementViewSet, AdminAchievementViewSet

router = DefaultRouter()
router.register(r'achievements', AchievementViewSet, basename='achievement')
router.register(r'admin/achievements', AdminAchievementViewSet, basename='admin-achievement')

urlpatterns = [
    path('', include(router.urls)),
]
