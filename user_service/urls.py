from django.urls import path
from .views import UserProfileView, UserSettingsView, UserAvatarView, AdminUserProfileView

urlpatterns = [
    path("", UserProfileView.as_view(), name="user-profile"),
    path("settings", UserSettingsView.as_view(), name="user-settings"),
    path("avatar", UserAvatarView.as_view(), name="user-avatar"),
    path("<int:user_id>/", AdminUserProfileView.as_view(), name="admin-user-profile"),
]
