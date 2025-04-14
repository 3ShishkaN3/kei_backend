from django.urls import path
from .views import ConsultationRequestView

urlpatterns = [
    path("consultation/", ConsultationRequestView.as_view(), name="consultation-request"),
]
