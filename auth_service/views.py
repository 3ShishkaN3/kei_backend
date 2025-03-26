import datetime
from django.contrib.auth import login, logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, permissions
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from .models import ConfirmationCode, User
from .tasks import send_confirmation_email_task
from .serializers import (
    RegisterSerializer, 
    LoginSerializer, 
    UserSerializer, 
    ConfirmEmailSerializer,
    RequestPasswordResetSerializer,
    ConfirmPasswordResetSerializer,
    RequestEmailChangeSerializer,
    ConfirmEmailChangeSerializer,
    EmptySerializer,
)

class RegisterView(GenericAPIView):
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.REGISTRATION,
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            send_confirmation_email_task.delay(user.email, confirmation.code, "registration")
            return Response(
                {
                    "user": UserSerializer(user).data,
                    "message": "Пользователь создан. На указанный email отправлен код подтверждения регистрации."
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data
            login(request, user)
            return Response({"message": "Вы успешно вошли"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request):
        logout(request)
        return Response({"message": "Вы успешно вышли"}, status=status.HTTP_200_OK)


class UserRoleView(GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserSerializer

    def patch(self, request, user_id):
        user = User.objects.get(id=user_id)
        if request.user.role == "admin":
            user.role = request.data.get("role", user.role)
            user.is_active = request.data.get("is_active", user.is_active)
        elif request.user.role == "teacher":
            if user.role == "student":
                user.role = "assistant"
            elif user.role == "assistant":
                user.role = "student"
            else:
                return Response({"error": "Недостаточно прав"}, status=status.HTTP_403_FORBIDDEN)
        user.save()
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class RegistrationConfirmView(GenericAPIView):
    serializer_class = ConfirmEmailSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            confirmation = serializer.validated_data["confirmation"]
            user.is_active = True
            user.save()
            confirmation.delete()
            return Response({"message": "Email успешно подтверждён."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestPasswordResetView(GenericAPIView):
    serializer_class = RequestPasswordResetSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            user = User.objects.get(email=email)
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.PASSWORD_CHANGE,
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            send_confirmation_email_task.delay(user.email, confirmation.code, "password_change")
            return Response({"message": "Код подтверждения отправлен на email."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfirmPasswordResetView(GenericAPIView):
    serializer_class = ConfirmPasswordResetSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            confirmation = serializer.validated_data["confirmation"]
            new_password = serializer.validated_data["new_password"]
            user.set_password(new_password)
            user.save()
            confirmation.delete()
            return Response({"message": "Пароль успешно изменён."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestEmailChangeView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RequestEmailChangeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            new_email = serializer.validated_data["new_email"]
            user = request.user
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.EMAIL_CHANGE,
                target_email=new_email,
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            send_confirmation_email_task.delay(new_email, confirmation.code, "email_change")
            return Response({"message": "Код подтверждения отправлен на новый email."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfirmEmailChangeView(GenericAPIView):
    serializer_class = ConfirmEmailChangeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            new_email = serializer.validated_data["new_email"]
            confirmation = serializer.validated_data["confirmation"]
            
            if User.objects.filter(email=new_email).exists():
                return Response({"error": "Этот email уже используется."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                user.email = new_email
                user.save()
                confirmation.delete()
                return Response({"message": "Email успешно изменён."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
