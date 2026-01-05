from django.core.files.storage import default_storage
from rest_framework.generics import RetrieveUpdateDestroyAPIView, RetrieveUpdateAPIView
from rest_framework.views import APIView
from rest_framework.decorators import action
from .models import UserProfile, UserSettings
from .serializers import UserProfileSerializer, UserSettingsSerializer, UserAvatarSerializer
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from rest_framework import status
from django.shortcuts import get_object_or_404
from auth_service.models import User
from auth_service.serializers import UserSerializer

class UserProfileView(RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        user_id = self.request.query_params.get('user_id')
        
        if user_id and self.request.user.role in ['admin', 'teacher']:
            target_user = get_object_or_404(User, id=user_id)
            profile, _ = UserProfile.objects.get_or_create(user=target_user)
            return profile
        
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile

    @swagger_auto_schema(responses={200: UserProfileSerializer})
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @swagger_auto_schema(responses={200: "Данные обновлены"})
    def put(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        
        if user_id and request.user.role != 'admin':
            return Response(
                {"error": "Нет прав для редактирования профиля другого пользователя"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return super().put(request, *args, **kwargs)

    @swagger_auto_schema(responses={200: "Профиль очищен"})
    def delete(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        
        if user_id and request.user.role != 'admin':
            return Response(
                {"error": "Нет прав для очистки профиля другого пользователя"},
                status=status.HTTP_403_FORBIDDEN
            )
        
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
        user_id = self.request.query_params.get('user_id')
        
        if user_id and self.request.user.role in ['admin', 'teacher']:
            target_user = get_object_or_404(User, id=user_id)
            profile, _ = UserProfile.objects.get_or_create(user=target_user)
            return profile
        
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
        user_id = request.query_params.get('user_id')
        
        if user_id and request.user.role != 'admin':
            return Response(
                {"error": "Нет прав для изменения аватара другого пользователя"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return super().put(request, *args, **kwargs)

    @swagger_auto_schema(
        responses={200: "Аватар удалён"},
        operation_description="Удалить аватар пользователя"
    )
    def delete(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        
        if user_id and request.user.role != 'admin':
            return Response(
                {"error": "Нет прав для удаления аватара другого пользователя"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        profile = self.get_object()
        if profile.avatar:
            profile.avatar.delete(save=False)
        profile.avatar = None
        profile.save()
        return Response({"message": "Аватар удалён"}, status=status.HTTP_200_OK)


class AdminUserProfileView(APIView):
    """
    Представление для просмотра и редактирования профилей других пользователей администратором.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, user_id):
        """
        Получение профиля пользователя.
        
        Доступно для администраторов и преподавателей.
        """
        if request.user.role not in ['admin', 'teacher']:
            return Response(
                {"error": "Нет прав для просмотра профилей других пользователей"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        target_user = get_object_or_404(User, id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        
        return Response({
            "user": UserSerializer(target_user).data,
            "profile": UserProfileSerializer(profile).data
        }, status=status.HTTP_200_OK)
    
    def put(self, request, user_id):
        """
        Обновление профиля пользователя.
        
        Доступно только для администраторов.
        """
        if request.user.role != 'admin':
            return Response(
                {"error": "Только администраторы могут редактировать профили других пользователей"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        target_user = get_object_or_404(User, id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "message": "Профиль успешно обновлён",
                "user": UserSerializer(target_user).data,
                "profile": serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
