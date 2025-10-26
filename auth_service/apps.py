from django.apps import AppConfig


class AuthServiceConfig(AppConfig):
    """
    Конфигурация приложения сервиса аутентификации.
    
    Определяет основные настройки Django приложения для управления
    пользователями, аутентификацией и авторизацией.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auth_service'
