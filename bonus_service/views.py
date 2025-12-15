from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from .models import Bonus, UserBonus
from .serializers import BonusSerializer, BuyBonusSerializer
from progress_service.models import LearningStats

class BonusViewSet(viewsets.ModelViewSet):
    queryset = Bonus.objects.all()
    serializer_class = BonusSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAdminUser()] # Or custom IsTeacher permission
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        # Only show video bonuses for now as per requirement, or all?
        # User said "Implement only 1st point", but placeholders for others.
        # So we can return all, and frontend handles display.
        return Bonus.objects.all().order_by('-created_at')

    @action(detail=True, methods=['post'])
    def buy(self, request, pk=None):
        bonus = self.get_object()
        user = request.user

        if UserBonus.objects.filter(user=user, bonus=bonus).exists():
            return Response({'detail': 'Bonus already purchased.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            stats = LearningStats.objects.get(user=user)
        except LearningStats.DoesNotExist:
            return Response({'detail': 'User stats not found.'}, status=status.HTTP_400_BAD_REQUEST)

        if stats.coins < bonus.price:
            return Response({'detail': 'Not enough coins.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            stats.coins -= bonus.price
            stats.save()
            UserBonus.objects.create(user=user, bonus=bonus)

        return Response({'detail': 'Bonus purchased successfully.', 'coins': stats.coins}, status=status.HTTP_200_OK)
