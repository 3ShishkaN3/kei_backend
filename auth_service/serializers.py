from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, ConfirmationCode, User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "email", "role", "is_active")

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password", "password2")

    def validate(self, attrs):
        attrs["email"] = attrs["email"].lower()  # Приведение email к нижнему регистру
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Пароли не совпадают"})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password2")
        user = User.objects.create_user(**validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        request = self.context.get("request")
        username = data.get("username") or data.get("email") 
        password = data.get("password")

        if not username or not password:
            raise serializers.ValidationError("Требуется username или email, а также пароль")

        user = authenticate(request=request, username=username, password=password)
        if not user:
            raise serializers.ValidationError("Неверный логин или пароль")
        if not user.is_active:
            raise serializers.ValidationError("Ваш аккаунт отключен")

        return user



class ConfirmEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        try:
            user = User.objects.get(email=data["email"].lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден.")
        qs = ConfirmationCode.objects.filter(user=user, code=data["code"], code_type=ConfirmationCode.REGISTRATION)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        data["user"] = user
        data["confirmation"] = confirmation
        return data

class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value.lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь с таким email не найден.")
        return value.lower()

class ConfirmPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    new_password2 = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        if data["new_password"] != data["new_password2"]:
            raise serializers.ValidationError("Пароли не совпадают.")
        try:
            user = User.objects.get(email=data["email"].lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден.")
        qs = ConfirmationCode.objects.filter(user=user, code=data["code"], code_type=ConfirmationCode.PASSWORD_CHANGE)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        data["user"] = user
        data["confirmation"] = confirmation
        return data

class RequestEmailChangeSerializer(serializers.Serializer):
    new_email = serializers.EmailField()

    def validate_new_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Этот email уже используется.")
        return value

class ConfirmEmailChangeSerializer(serializers.Serializer):
    current_email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate(self, data):
        try:
            user = User.objects.get(email=data["current_email"].lower())
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден.")
        qs = ConfirmationCode.objects.filter(user=user, code=data["code"], code_type=ConfirmationCode.EMAIL_CHANGE)
        if not qs.exists():
            raise serializers.ValidationError("Неверный код подтверждения.")
        confirmation = qs.first()
        if confirmation.is_expired():
            raise serializers.ValidationError("Код подтверждения истёк.")
        data["user"] = user
        data["new_email"] = confirmation.target_email
        data["confirmation"] = confirmation
        return data
    
class ResendRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower()
    
class EmptySerializer(serializers.Serializer):
    pass