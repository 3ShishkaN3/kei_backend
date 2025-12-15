"""
Сериализаторы для сервиса аутентификации.

Содержит сериализаторы для регистрации, входа, подтверждения email,
сброса и изменения паролей, а также управления профилем пользователя.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, ConfirmationCode, User


class UserSerializer(serializers.ModelSerializer):
    """Сериализатор для отображения данных пользователя."""
    
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "is_active")


class RegisterSerializer(serializers.ModelSerializer):
    """
    Сериализатор для регистрации новых пользователей.
    
    Включает валидацию паролей и автоматическую нормализацию email.
    """
    
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password", "password2")

    def validate(self, attrs):
        """
        Валидирует данные регистрации.
        
        Проверяет совпадение паролей и нормализует email к нижнему регистру.
        """
        # Нормализуем email для единообразия
        attrs["email"] = attrs["email"].lower()
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Пароли не совпадают"})
        return attrs

    def create(self, validated_data):
        """
        Создает нового пользователя.
        
        Удаляет password2 из данных и создает неактивного пользователя
        (активация происходит после подтверждения email).
        """
        validated_data.pop("password2")  # Удаляем дублирующее поле
        user = User.objects.create_user(**validated_data)
        return user


class LoginSerializer(serializers.Serializer):
    """
    Сериализатор для входа в систему.
    
    Поддерживает вход как по username, так и по email.
    """
    
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        """
        Валидирует данные входа и аутентифицирует пользователя.
        
        Проверяет наличие учетных данных, аутентифицирует пользователя
        и проверяет активность аккаунта.
        """
        request = self.context.get("request")
        # Поддерживаем вход как по username, так и по email
        username = data.get("username") or data.get("email") 
        password = data.get("password")

        if not username or not password:
            raise serializers.ValidationError("Требуется username или email, а также пароль")

        # Аутентифицируем пользователя
        user = authenticate(request=request, username=username, password=password)
        if not user:
            raise serializers.ValidationError("Неверный логин или пароль")
        if not user.is_active:
            raise serializers.ValidationError("Ваш аккаунт отключен")

        return user


class ConfirmEmailSerializer(serializers.Serializer):
    """
    Сериализатор для подтверждения email при регистрации.
    
    Проверяет код подтверждения и активирует аккаунт пользователя.
    """
    
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        """
        Валидирует код подтверждения регистрации.
        
        Проверяет существование пользователя, валидность кода
        и его срок действия.
        """
        try:
            user = User.objects.get(email=data["email"].lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден.")
        
        # Ищем активный код подтверждения регистрации
        qs = ConfirmationCode.objects.filter(user=user, code=data["code"], code_type=ConfirmationCode.REGISTRATION)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        
        # Добавляем объекты в validated_data для использования в view
        data["user"] = user
        data["confirmation"] = confirmation
        return data


class RequestPasswordResetSerializer(serializers.Serializer):
    """
    Сериализатор для запроса сброса пароля.
    
    Проверяет существование пользователя с указанным email.
    """
    
    email = serializers.EmailField()

    def validate_email(self, value):
        """
        Валидирует email и проверяет существование пользователя.
        
        Возвращает нормализованный email в нижнем регистре.
        """
        try:
            user = User.objects.get(email=value.lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден.")
        return value.lower()


class ConfirmPasswordResetSerializer(serializers.Serializer):
    """
    Сериализатор для подтверждения сброса пароля.
    
    Проверяет код подтверждения и валидирует новый пароль.
    """
    
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        """
        Валидирует данные сброса пароля.
        
        Проверяет совпадение паролей, существование пользователя,
        валидность кода подтверждения и его срок действия.
        """
        if data["new_password"] != data["new_password2"]:
            raise serializers.ValidationError("Пароли не совпадают.")
        
        try:
            user = User.objects.get(email=data["email"].lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден.")
        
        # Ищем активный код подтверждения смены пароля
        qs = ConfirmationCode.objects.filter(user=user, code=data["code"], code_type=ConfirmationCode.PASSWORD_CHANGE)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        
        # Добавляем объекты в validated_data для использования в view
        data["user"] = user
        data["confirmation"] = confirmation
        data["new_password"] = data["new_password"]
        return data


class RequestEmailChangeSerializer(serializers.Serializer):
    """
    Сериализатор для запроса смены email.
    
    Проверяет доступность нового email и пароль пользователя.
    """
    
    new_email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_new_email(self, value):
        """
        Проверяет, что новый email не занят другим пользователем.
        """
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("Этот email уже используется.")
        return value.lower()

    def validate(self, data):
        """
        Проверяет пароль текущего пользователя.
        """
        if not self.context['request'].user.check_password(data['password']):
            raise serializers.ValidationError({"password": "Неверный пароль."})
        return data


class ConfirmEmailChangeSerializer(serializers.Serializer):
    """
    Сериализатор для подтверждения смены email.
    
    Проверяет код подтверждения и обновляет email пользователя.
    """
    
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        """
        Валидирует код подтверждения смены email.
        
        Проверяет валидность кода и его срок действия.
        """
        # Ищем активный код подтверждения смены email
        qs = ConfirmationCode.objects.filter(code=data["code"], code_type=ConfirmationCode.EMAIL_CHANGE)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        
        # Добавляем объекты в validated_data для использования в view
        data["user"] = confirmation.user
        data["new_email"] = confirmation.target_email
        data["confirmation"] = confirmation
        return data


class RequestPasswordChangeSerializer(serializers.Serializer):
    """
    Сериализатор для запроса смены пароля авторизованным пользователем.
    
    Проверяет текущий пароль пользователя.
    """
    
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, data):
        """
        Проверяет текущий пароль пользователя.
        """
        if not self.context['request'].user.check_password(data['current_password']):
            raise serializers.ValidationError({"current_password": "Неверный пароль."})
        return data


class ConfirmPasswordChangeSerializer(serializers.Serializer):
    """
    Сериализатор для подтверждения смены пароля.
    
    Проверяет код подтверждения и обновляет пароль пользователя.
    """
    
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        """
        Валидирует код подтверждения смены пароля.
        
        Проверяет валидность кода и его срок действия.
        """
        # Ищем активный код подтверждения смены пароля
        qs = ConfirmationCode.objects.filter(code=data["code"], code_type=ConfirmationCode.PASSWORD_CHANGE)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        
        # Добавляем объекты в validated_data для использования в view
        data["user"] = confirmation.user
        data["new_password"] = confirmation.target_password
        data["confirmation"] = confirmation
        return data


class ResendRegisterSerializer(serializers.Serializer):
    """
    Сериализатор для повторной отправки кода подтверждения регистрации.
    
    Нормализует email к нижнему регистру.
    """
    
    email = serializers.EmailField()

    def validate_email(self, value):
        """
        Нормализует email к нижнему регистру.
        """
        return value.lower()


class EmptySerializer(serializers.Serializer):
    """
    Пустой сериализатор для операций без данных.
    
    Используется для logout и других операций, не требующих входных данных.
    """
    pass