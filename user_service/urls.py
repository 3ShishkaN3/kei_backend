from django.urls import path
from .views import UserProfileView, UserSettingsView, UserAvatarView

urlpatterns = [
    path("", UserProfileView.as_view(), name="user-profile"),
    path("settings", UserSettingsView.as_view(), name="user-settings"),
    path("avatar", UserAvatarView.as_view(), name="user-avatar"),
]
