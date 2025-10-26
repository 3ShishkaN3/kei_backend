from django.core.files.storage import default_storage
from rest_framework.generics import RetrieveUpdateDestroyAPIView, RetrieveUpdateAPIView
from .models import UserProfile, UserSettings
from .serializers import UserProfileSerializer, UserSettingsSerializer, UserAvatarSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import status

class UserProfileView(RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    @swagger_auto_schema(responses={200: UserProfileSerializer})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(responses={200: "Данные обновлены"})
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @swagger_auto_schema(responses={200: "Профиль очищен"})
    def delete(self, request, *args, **kwargs):
        profile = self.get_object()
        profile.clear_fields()
        return Response({"message": "Профиль очищен"}, status=status.HTTP_200_OK)

class UserSettingsView(RetrieveUpdateAPIView):
    serializer_class = UserSettingsSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        settings, _ = UserSettings.objects.get_or_create(user=self.request.user)
        return settings

class UserAvatarView(RetrieveUpdateDestroyAPIView):
    serializer_class = UserAvatarSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    @swagger_auto_schema(
        responses={200: UserAvatarSerializer},
        operation_description="Получить текущий аватар пользователя"
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'avatar': openapi.Schema(type=openapi.TYPE_FILE)
            },
        ),
        responses={200: "Аватар обновлён"},
        operation_description="Загрузить новый аватар"
    )
    def put(self, request, *args, **kwargs):
        return super().put(request, *args, **kwargs)

    @swagger_auto_schema(
        responses={200: "Аватар удалён"},
        operation_description="Удалить аватар пользователя"
    )
    def delete(self, request, *args, **kwargs):
        profile = self.get_object()
        if profile.avatar:
            profile.avatar.delete(save=False)
        profile.avatar = None
        profile.save()
        return Response({"message": "Аватар удалён"}, status=status.HTTP_200_OK)
