from django.urls import path
from . import views

urlpatterns = [
    path('status/', views.challenge_status, name='challenge-status'),
    path('generate/', views.challenge_generate, name='challenge-generate'),
    path('history/', views.challenge_history, name='challenge-history'),
    path('<int:challenge_id>/', views.challenge_detail, name='challenge-detail'),
    path('<int:challenge_id>/complete/', views.challenge_complete, name='challenge-complete'),
]
