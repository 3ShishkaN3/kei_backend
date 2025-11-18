"""
Представления для сервиса аутентификации.

Содержит API endpoints для регистрации, входа, управления пользователями,
подтверждения email, сброса и изменения паролей.
"""

import datetime
from django.contrib.auth import login, logout
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password
from rest_framework import status, permissions
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from .models import ConfirmationCode, User
from .tasks import send_confirmation_email_task
from django.middleware.csrf import get_token
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework import filters
from django.db.models import Q
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
    ResendRegisterSerializer,
    RequestPasswordChangeSerializer,
    ConfirmPasswordChangeSerializer,
    AdminCreateUserSerializer,
    AdminUpdateUserSerializer,
    BulkUserOperationSerializer,
)


class CSRFTokenView(APIView):
    """
    Представление для получения CSRF токена.
    
    Предоставляет CSRF токен для защиты от CSRF атак при работе с API.
    """
    
    def get(self, request, *args, **kwargs):
        """Возвращает CSRF токен для текущей сессии."""
        csrf_token = get_token(request)
        return Response({"csrf_token": csrf_token}, status=status.HTTP_200_OK)


class RegisterView(GenericAPIView):
    """
    Представление для регистрации новых пользователей.
    
    Создает неактивного пользователя и отправляет код подтверждения на email.
    Обрабатывает повторные запросы регистрации для неактивированных аккаунтов.
    """
    
    serializer_class = RegisterSerializer

    def post(self, request):
        """
        Обрабатывает запрос регистрации.
        
        Проверяет существование пользователя, создает нового пользователя
        или обрабатывает повторную отправку кода для неактивированных аккаунтов.
        """
        data = request.data.copy()
        data["email"] = data.get("email", "").lower()
        username = data.get("username")
        email = data.get("email")

        # Проверяем, существует ли уже пользователь с такими данными
        try:
            user = User.objects.get(email=email, username=username)

            # Если пользователь неактивен и недавно зарегистрирован, 
            # и у него есть активные коды подтверждения
            if (
                not user.is_active and 
                (timezone.now() - user.date_joined) < datetime.timedelta(minutes=25) and 
                user.confirmation_codes.filter(expires_at__gt=timezone.now()).exists()
            ):
                return Response(
                    {"message": "Ожидает подтверждения"},
                    status=status.HTTP_200_OK
                )
        except User.DoesNotExist:
            pass

        # Создаем нового пользователя
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            # Создаем код подтверждения с увеличенным временем жизни (20 минут)
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.REGISTRATION,
                expires_at=timezone.now() + datetime.timedelta(minutes=20)
            )
            # Отправляем код подтверждения асинхронно
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
    """
    Представление для входа в систему.
    
    Аутентифицирует пользователя и создает сессию.
    """
    
    serializer_class = LoginSerializer

    def post(self, request):
        """
        Обрабатывает запрос входа в систему.
        
        Валидирует учетные данные и создает сессию пользователя.
        """
        serializer = self.get_serializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            user = serializer.validated_data
            login(request, user)  # Создаем сессию пользователя
            return Response({"message": "Вы успешно вошли"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserView(APIView):
    """
    Представление для получения данных текущего пользователя.
    
    Возвращает информацию о авторизованном пользователе.
    """
    
    def get(self, request):
        """
        Возвращает данные текущего пользователя.
        
        Проверяет авторизацию и возвращает сериализованные данные пользователя.
        """
        if request.user.is_authenticated:
            return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "Пользователь не авторизован."}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(GenericAPIView):
    """
    Представление для выхода из системы.
    
    Завершает сессию пользователя.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EmptySerializer

    def post(self, request):
        """
        Обрабатывает запрос выхода из системы.
        
        Завершает сессию пользователя.
        """
        logout(request)  # Завершаем сессию
        return Response({"message": "Вы успешно вышли"}, status=status.HTTP_200_OK)


class UserRoleView(GenericAPIView):
    """
    Представление для управления ролями пользователей.
    
    Позволяет администраторам и преподавателям изменять роли пользователей.
    """
    
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserSerializer

    def patch(self, request, user_id):
        """
        Обновляет роль и статус пользователя.
        
        Администраторы могут изменять любые роли и статусы.
        Преподаватели могут только переключать между ролями student и assistant.
        """
        user = User.objects.get(id=user_id)
        if request.user.role == "admin":
            # Администраторы имеют полные права
            user.role = request.data.get("role", user.role)
            user.is_active = request.data.get("is_active", user.is_active)
        elif request.user.role == "teacher":
            # Преподаватели могут только переключать между student и assistant
            if user.role == "student":
                user.role = "assistant"
            elif user.role == "assistant":
                user.role = "student"
            else:
                return Response({"error": "Недостаточно прав"}, status=status.HTTP_403_FORBIDDEN)
        user.save()
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class StudentsPagination(PageNumberPagination):
    """Пагинация для списка учеников."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class StudentsListView(APIView):
    """
    Представление для получения списка учеников с расширенной фильтрацией.
    
    Позволяет администраторам и преподавателям получать список учеников
    с фильтрацией по статусу активности, поиском и пагинацией.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StudentsPagination
    
    def get(self, request):
        """
        Возвращает список учеников с возможностью фильтрации.
        
        Доступно только для администраторов и преподавателей.
        
        Параметры запроса:
        - is_active: true/false - фильтр по статусу активности (по умолчанию только активные)
        - search: строка поиска по username или email
        - role: фильтр по роли (по умолчанию student)
        """
        
        if request.user.role not in ["admin", "teacher"]:
            return Response(
                {"error": "Недостаточно прав"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Фильтр по роли (по умолчанию только студенты)
        role_param = request.query_params.get('role')
        if role_param:
            try:
                queryset = User.objects.filter(role=role_param)
            except ValueError:
                queryset = User.objects.filter(role=User.Role.STUDENT)
        else:
            queryset = User.objects.filter(role=User.Role.STUDENT)
        
        # Фильтр по активности (по умолчанию только активные, если не указано явно)
        is_active_param = request.query_params.get('is_active')
        
        if is_active_param is None:
            # По умолчанию показываем только активных
            queryset = queryset.filter(is_active=True)
        elif is_active_param.lower() in ['true', 'false']:
            queryset = queryset.filter(is_active=(is_active_param.lower() == 'true'))
        
        # Поиск по username или email
        search = request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
            )
        
        # Сортировка
        ordering = request.query_params.get('ordering', 'username')
        if ordering.lstrip('-') in ['username', 'email', 'date_joined', 'last_login']:
            queryset = queryset.order_by(ordering)
        else:
            queryset = queryset.order_by('username')
        
        # Пагинация
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = UserSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = UserSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RegistrationConfirmView(GenericAPIView):
    """
    Представление для подтверждения регистрации.
    
    Активирует аккаунт пользователя после ввода правильного кода подтверждения.
    """
    
    serializer_class = ConfirmEmailSerializer

    def post(self, request):
        """
        Подтверждает регистрацию пользователя.
        
        Активирует аккаунт и удаляет использованный код подтверждения.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            confirmation = serializer.validated_data["confirmation"]
            user.is_active = True  # Активируем аккаунт
            user.save()
            confirmation.delete()  # Удаляем использованный код
            return Response({"message": "Email успешно подтверждён."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestPasswordResetView(GenericAPIView):
    """
    Представление для запроса сброса пароля.
    
    Отправляет код подтверждения на email для сброса пароля.
    """
    
    serializer_class = RequestPasswordResetSerializer

    def post(self, request):
        """
        Обрабатывает запрос сброса пароля.
        
        Создает код подтверждения и отправляет его на email пользователя.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            user = User.objects.get(email=email)
            # Создаем код подтверждения смены пароля
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.PASSWORD_CHANGE,
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            # Отправляем код подтверждения асинхронно
            send_confirmation_email_task.delay(user.email, confirmation.code, "password_change")
            return Response({"message": "Код подтверждения отправлен на email."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfirmPasswordResetView(GenericAPIView):
    """
    Представление для подтверждения сброса пароля.
    
    Устанавливает новый пароль после ввода правильного кода подтверждения.
    """
    
    serializer_class = ConfirmPasswordResetSerializer

    def post(self, request):
        """
        Подтверждает сброс пароля.
        
        Устанавливает новый пароль и удаляет использованный код подтверждения.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            confirmation = serializer.validated_data["confirmation"]
            new_password = serializer.validated_data["new_password"]
            user.set_password(new_password)  # Хешируем и устанавливаем новый пароль
            user.save()
            confirmation.delete()  # Удаляем использованный код
            return Response({"message": "Пароль успешно изменён."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestEmailChangeView(GenericAPIView):
    """
    Представление для запроса смены email.
    
    Отправляет код подтверждения на новый email для смены email.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RequestEmailChangeSerializer

    def post(self, request):
        """
        Обрабатывает запрос смены email.
        
        Создает код подтверждения и отправляет его на новый email.
        """
        serializer = self.get_serializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            new_email = serializer.validated_data["new_email"]
            user = request.user
            # Создаем код подтверждения смены email
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.EMAIL_CHANGE,
                target_email=new_email,  # Сохраняем новый email
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            # Отправляем код подтверждения на новый email
            send_confirmation_email_task.delay(new_email, confirmation.code, "email_change")
            return Response({"message": "Код подтверждения отправлен на новый email."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfirmEmailChangeView(GenericAPIView):
    """
    Представление для подтверждения смены email.
    
    Обновляет email пользователя после ввода правильного кода подтверждения.
    """
    
    serializer_class = ConfirmEmailChangeSerializer

    def post(self, request):
        """
        Подтверждает смену email.
        
        Обновляет email пользователя и удаляет использованный код подтверждения.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            new_email = serializer.validated_data["new_email"]
            confirmation = serializer.validated_data["confirmation"]

            # Проверяем, что новый email не занят
            if User.objects.filter(email=new_email).exists():
                return Response({"error": "Этот email уже используется."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                user.email = new_email
                user.save()
                confirmation.delete()  # Удаляем использованный код
                return Response({"message": "Email успешно изменён."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RegisterResendView(GenericAPIView):
    """
    Представление для повторной отправки кода подтверждения регистрации.
    
    Отправляет новый код подтверждения для неактивированных аккаунтов.
    """
    
    serializer_class = ResendRegisterSerializer

    def post(self, request):
        """
        Обрабатывает запрос повторной отправки кода подтверждения.
        
        Проверяет существование пользователя и отправляет новый код подтверждения.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data["email"]
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({"error": "Пользователь с таким email не найден."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Проверяем, что аккаунт еще не активирован
            if user.is_active:
                return Response({"error": "Аккаунт уже активирован."}, status=status.HTTP_400_BAD_REQUEST)
            
            # Создаем новый код подтверждения
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.REGISTRATION,
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            # Отправляем новый код подтверждения
            send_confirmation_email_task.delay(user.email, confirmation.code, "registration")
            return Response({"message": "Код подтверждения повторно отправлен."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RequestPasswordChangeView(GenericAPIView):
    """
    Представление для запроса смены пароля авторизованным пользователем.
    
    Отправляет код подтверждения на email для смены пароля.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RequestPasswordChangeSerializer

    def post(self, request):
        """
        Обрабатывает запрос смены пароля.
        
        Создает код подтверждения с хешированным новым паролем и отправляет его на email.
        """
        serializer = self.get_serializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            new_password = serializer.validated_data["new_password"]
            # Хешируем новый пароль для безопасного хранения в коде подтверждения
            hashed_new_password = make_password(new_password)
            # Создаем код подтверждения с хешированным паролем
            confirmation = ConfirmationCode.objects.create(
                user=user,
                code_type=ConfirmationCode.PASSWORD_CHANGE,
                target_password=hashed_new_password,  # Сохраняем хешированный пароль
                expires_at=timezone.now() + datetime.timedelta(minutes=10)
            )
            # Отправляем код подтверждения
            send_confirmation_email_task.delay(user.email, confirmation.code, "password_change")
            return Response({"message": "Код подтверждения для смены пароля отправлен на вашу почту."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConfirmPasswordChangeView(GenericAPIView):
    """
    Представление для подтверждения смены пароля.
    
    Устанавливает новый пароль после ввода правильного кода подтверждения.
    """
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ConfirmPasswordChangeSerializer

    def post(self, request):
        """
        Подтверждает смену пароля.
        
        Устанавливает новый пароль из кода подтверждения и удаляет использованный код.
        """
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data["user"]
            new_password = serializer.validated_data["new_password"]
            confirmation = serializer.validated_data["confirmation"]

            # Устанавливаем новый пароль (уже хешированный из кода подтверждения)
            user.password = new_password
            user.save()
            confirmation.delete()  # Удаляем использованный код
            return Response({"message": "Пароль успешно изменён."})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet для управления пользователями администратором.
    
    Предоставляет полный CRUD для пользователей, доступный только администраторам.
    """
    
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.all()
    serializer_class = UserSerializer
    lookup_field = 'id'
    pagination_class = StudentsPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['username', 'email']
    ordering_fields = ['username', 'email', 'date_joined', 'last_login']
    ordering = ['username']
    
    def get_serializer_class(self):
        """Возвращает соответствующий сериализатор в зависимости от действия."""
        if self.action == 'create':
            return AdminCreateUserSerializer
        elif self.action in ['update', 'partial_update']:
            return AdminUpdateUserSerializer
        elif self.action == 'bulk_operation':
            return BulkUserOperationSerializer
        return UserSerializer
    
    def get_queryset(self):
        """Возвращает queryset с возможностью фильтрации."""
        queryset = User.objects.all()
        
        # Фильтр по роли
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role=role)

        is_active_param = self.request.query_params.get('is_active', "False")
        
        if is_active_param is not None and is_active_param.lower() in ['true', 'false']:
            if is_active_param.lower() == 'true': queryset = queryset.filter(is_active=True)
        else:
            queryset = queryset.filter(is_active=True)
        
        search = self.request.query_params.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) | Q(email__icontains=search)
            )
        
        return queryset.order_by('username')
    
    def retrieve(self, request, *args, **kwargs):
        """Получение детальной информации о пользователе."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        """Удаление пользователя."""
        instance = self.get_object()
        
        # Защита от удаления самого себя
        if instance.id == request.user.id:
            return Response(
                {"error": "Нельзя удалить свой собственный аккаунт"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.delete()
        return Response(
            {"message": "Пользователь успешно удалён"},
            status=status.HTTP_204_NO_CONTENT
        )
    
    @action(detail=False, methods=['post'], serializer_class=BulkUserOperationSerializer)
    def bulk_operation(self, request):
        """
        Массовые операции с пользователями.
        
        Действия:
        - activate: активация пользователей
        - deactivate: деактивация пользователей
        - delete: удаление пользователей
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user_ids = serializer.validated_data['user_ids']
        action_type = serializer.validated_data['action']
        
        users = User.objects.filter(id__in=user_ids)
        
        # Защита от удаления/деактивации самого себя
        if request.user.id in user_ids and action_type in ['delete', 'deactivate']:
            return Response(
                {"error": "Нельзя выполнить это действие со своим собственным аккаунтом"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action_type == 'activate':
            updated = users.update(is_active=True)
            return Response({
                "message": f"Активировано пользователей: {updated}",
                "updated_count": updated
            }, status=status.HTTP_200_OK)
        
        elif action_type == 'deactivate':
            updated = users.update(is_active=False)
            return Response({
                "message": f"Деактивировано пользователей: {updated}",
                "updated_count": updated
            }, status=status.HTTP_200_OK)
        
        elif action_type == 'delete':
            count = users.count()
            users.delete()
            return Response({
                "message": f"Удалено пользователей: {count}",
                "deleted_count": count
            }, status=status.HTTP_200_OK)
        
        return Response(
            {"error": "Неизвестное действие"},
            status=status.HTTP_400_BAD_REQUEST
        )