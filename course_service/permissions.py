from rest_framework import permissions

class IsAdminTeacherOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role in ['admin', 'teacher']


class IsAdminTeacherAssistantOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.role in ['admin', 'teacher', 'assistant']

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        if request.user.role in ['admin', 'teacher']:
            return True
        
        if request.user.role == 'assistant':
            return obj.assistants.filter(assistant=request.user).exists()
        
        return False
