from datetime import datetime

from django.db.models import Q
from rest_framework import viewsets, permissions
from rest_framework.response import Response

from auth_service.models import User
from .models import Event, DayNote
from .serializers import EventSerializer, DayNoteSerializer


class IsAdminOrTeacherOrOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        if request.user.role in ["admin", "teacher"]:
            return True
        if isinstance(obj, Event):
            # Админ/преподаватель
            if obj.created_by_id == request.user.id:
                return True
            return obj.participants.filter(user_id=request.user.id).exists()
        if isinstance(obj, DayNote):
            return obj.user_id == request.user.id
        return False

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [IsAdminOrTeacherOrOwner]

    def get_queryset(self):
        user: User = self.request.user
        qs = Event.objects.all().order_by("-start_at")

        # Доступ: не админ/преподаватель видит только свои события или участвующие в них
        if user.role not in ["admin", "teacher"]:
            qs = qs.filter(Q(created_by=user) | Q(participants__user=user)).distinct()

        # Фильтры
        participant_id = self.request.query_params.get("participant_id")
        status_param = self.request.query_params.get("status")
        created_by_id = self.request.query_params.get("created_by_id")
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")

        if participant_id:
            qs = qs.filter(participants__user_id=participant_id)
        if status_param:
            qs = qs.filter(status=status_param)
        if created_by_id:
            qs = qs.filter(created_by_id=created_by_id)
        if date_from:
            try:
                qs = qs.filter(end_at__gte=datetime.fromisoformat(date_from))
            except Exception:
                pass
        if date_to:
            try:
                qs = qs.filter(start_at__lte=datetime.fromisoformat(date_to))
            except Exception:
                pass
        return qs.distinct()

    def perform_create(self, serializer):
        serializer.save()


class DayNoteViewSet(viewsets.ModelViewSet):
    serializer_class = DayNoteSerializer
    permission_classes = [IsAdminOrTeacherOrOwner]

    def get_queryset(self):
        user: User = self.request.user
        qs = DayNote.objects.all().order_by("-date", "-created_at")
        # Не админ/преподаватель может только просматривать свои заметки
        if user.role not in ["admin", "teacher"]:
            qs = qs.filter(user=user)
        else:
            user_id = self.request.query_params.get("user_id")
            if user_id:
                qs = qs.filter(user_id=user_id)
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        if date_from:
            try:
                qs = qs.filter(date__gte=date_from)
            except Exception:
                pass
        if date_to:
            try:
                qs = qs.filter(date__lte=date_to)
            except Exception:
                pass
        return qs

    def perform_create(self, serializer):
        serializer.save()


