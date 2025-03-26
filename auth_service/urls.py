from django.urls import path
from .views import (
    RegisterView, LoginView, LogoutView, UserRoleView,
    RegistrationConfirmView, RequestPasswordResetView, ConfirmPasswordResetView,
    RequestEmailChangeView, ConfirmEmailChangeView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("user/<int:user_id>/role/", UserRoleView.as_view(), name="user-role"),
    
    # Подтверждение регистрации по email
    path("register/confirm/", RegistrationConfirmView.as_view(), name="register-confirm"),
    
    # Смена пароля
    path("password/reset/request/", RequestPasswordResetView.as_view(), name="password-reset-request"),
    path("password/reset/confirm/", ConfirmPasswordResetView.as_view(), name="password-reset-confirm"),
    
    # Смена email
    path("email/change/request/", RequestEmailChangeView.as_view(), name="email-change-request"),
    path("email/change/confirm/", ConfirmEmailChangeView.as_view(), name="email-change-confirm"),
]
