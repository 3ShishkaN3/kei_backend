from rest_framework import permissions


class IsAdminOrTeacher(permissions.BasePermission):
    """Allow admin and teacher to create/update/delete bonuses."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_staff or getattr(request.user, "role", None) in ("admin", "teacher")
