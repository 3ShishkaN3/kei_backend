from django.urls import path, re_path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf.urls.static import static
from django.conf import settings

schema_view = get_schema_view(
    openapi.Info(
        title="Auth API",
        default_version="v1",
        description="Документация API авторизации",
        contact=openapi.Contact(email="noreply@keisenpai.com"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

BASE_URL = 'api'
API_VERSION = 1

urlpatterns = [
    re_path(r"^swagger(?P<format>\.json|\.yaml)$", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path(f"{BASE_URL}/v{API_VERSION}/auth/", include("auth_service.urls")),
    path(f"{BASE_URL}/v{API_VERSION}/telegram/", include("telegram_service.urls")),
    path(f"{BASE_URL}/v{API_VERSION}/profile/", include("user_service.urls")),
    path(f"{BASE_URL}/v{API_VERSION}/courses/", include("course_service.urls")),
    path(f"{BASE_URL}/v{API_VERSION}/lessons/", include("lesson_service.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
