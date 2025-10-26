"""
Backend аутентификации для сервиса аутентификации.

Содержит кастомный backend для аутентификации пользователей
как по username, так и по email адресу.
"""

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Кастомный backend аутентификации.
    
    Позволяет пользователям входить в систему как по username,
    так и по email адресу. Автоматически определяет тип входа
    по наличию символа '@' в поле username.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Аутентифицирует пользователя по username или email.
        
        Проверяет наличие символа '@' в username для определения
        типа аутентификации (email или username).
        
        Args:
            request: HTTP запрос
            username (str): Username или email пользователя
            password (str): Пароль пользователя
            **kwargs: Дополнительные параметры
            
        Returns:
            User: Аутентифицированный пользователь или None
        """
        if username is None:
            return None
            
        user = None
        # Определяем тип аутентификации по наличию '@' в username
        if "@" in username:
            # Аутентификация по email
            try:
                user = User.objects.get(email=username.lower())
            except User.DoesNotExist:
                return None
        else:
            # Аутентификация по username
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return None

        # Проверяем пароль и возвращаем пользователя
        if user and user.check_password(password):
            return user
        return None
