from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BonusViewSet

router = DefaultRouter()
router.register(r'bonuses', BonusViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
