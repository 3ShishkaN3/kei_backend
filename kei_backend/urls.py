from django.urls import path, re_path, include
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.conf.urls.static import static
from django.conf import settings
from django.http import JsonResponse
from django.db import connection

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

def health_check(request):
    status = {"status": "ok", "database": "ok"}
    try:
        connection.ensure_connection()
    except Exception as e:
        status["status"] = "error"
        status["database"] = str(e)
        return JsonResponse(status, status=503)
    return JsonResponse(status)

API_VERSION = 1
BASE_URL = f'api/v{API_VERSION}' 

api_urlpatterns = [
    path("auth/", include("auth_service.urls")),
    path("telegram/", include("telegram_service.urls")),
    path("profile/", include("user_service.urls")),
    path("courses/", include("course_service.urls")),
    path("lessons/", include("lesson_service.urls")),
    path("materials/", include("material_service.urls")),
    path("dict/", include("dict_service.urls")),
    path("progress/", include("progress_service.urls")),
    path("calendar/", include("calendar_service.urls")),
    path("achievements/", include("achievement_service.urls")),
    path("bonuses/", include("bonus_service.urls")),
]

urlpatterns = [
    path("health/", health_check, name="health_check"),
    re_path(r"^swagger(?P<format>\.json|\.yaml)$", schema_view.without_ui(cache_timeout=0), name="schema-json"),
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path(f"{BASE_URL}/", include(api_urlpatterns)),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
