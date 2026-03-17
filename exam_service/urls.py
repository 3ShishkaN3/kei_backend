from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ExamViewSet, ExamSectionViewSet, ExamSectionItemViewSet

router = DefaultRouter()
router.register(r'', ExamViewSet, basename='exam')

urlpatterns = [
    path('<int:exam_id>/sections/<int:section_id>/items/', ExamSectionItemViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='exam-section-items'),
    path('<int:exam_id>/sections/<int:section_id>/items/<int:pk>/', ExamSectionItemViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='exam-section-item-detail'),
    path('<int:exam_id>/sections/', ExamSectionViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='exam-sections'),
    path('<int:exam_id>/sections/<int:pk>/', ExamSectionViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='exam-section-detail'),
    path('', include(router.urls)),
]
