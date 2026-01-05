"""
URL конфигурация для сервиса аутентификации.

Определяет маршруты для всех API endpoints сервиса аутентификации,
включая регистрацию, вход, управление пользователями и подтверждения.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CSRFTokenView, RegisterView, LoginView, LogoutView, UserRoleView,
    RegistrationConfirmView, RequestPasswordResetView, ConfirmPasswordResetView,
    RequestEmailChangeView, ConfirmEmailChangeView, UserView, RegisterResendView,
    RequestPasswordChangeView, ConfirmPasswordChangeView, StudentsListView,
    UserViewSet,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='admin-user')

urlpatterns = [
    path("csrf-token/", CSRFTokenView.as_view(), name="csrf-token"),
    
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("user/<int:user_id>/role/", UserRoleView.as_view(), name="user-role"),
    path("user/", UserView.as_view(), name="user"),
    path("students/", StudentsListView.as_view(), name="students-list"),
    
    path("", include(router.urls)),
    
    path("register/confirm/", RegistrationConfirmView.as_view(), name="register-confirm"),
    path("register/resend/", RegisterResendView.as_view(), name="register-resend"),
    
    path("password/reset/request/", RequestPasswordResetView.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", ConfirmPasswordResetView.as_view(), name="password-reset-confirm"),
    path("password/change/request/", RequestPasswordChangeView.as_view(), name="password-change-request"),
    path("password/change/confirm/", ConfirmPasswordChangeView.as_view(), name="password-change-confirm"),

    path("email/change/request/", RequestEmailChangeView.as_view(), name="email-change-request"),
    path("email/change/confirm/", ConfirmEmailChangeView.as_view(), name="email-change-confirm"),
]
