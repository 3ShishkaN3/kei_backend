from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Achievement, UserAchievement
from .serializers import AchievementSerializer, AdminAchievementSerializer

class AchievementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for users to see achievements.
    """
    queryset = Achievement.objects.filter(is_active=True)
    serializer_class = AchievementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class AdminAchievementViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for admins to manage achievements.
    """
    queryset = Achievement.objects.all()
    serializer_class = AdminAchievementSerializer
    permission_classes = [permissions.IsAdminUser]
