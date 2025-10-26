"""
Модели для сервиса аутентификации.

Содержит модели User и ConfirmationCode для управления пользователями
и процессами подтверждения различных операций.
"""

import datetime
import random
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class User(AbstractUser):
    """
    Расширенная модель пользователя с дополнительными полями.
    
    Добавляет к стандартной модели Django User поля для роли,
    email и статуса активности с автоматической генерацией username.
    """
    
    class Role(models.TextChoices):
        """Роли пользователей в системе."""
        ADMIN = "admin", "Админ"
        TEACHER = "teacher", "Преподаватель"
        ASSISTANT = "assistant", "Помощник"
        STUDENT = "student", "Ученик"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT
    )

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        """
        Переопределяет сохранение для автоматической генерации username и нормализации email.
        
        Если username не задан, генерирует уникальный username на основе UUID.
        Приводит email к нижнему регистру для единообразия.
        """
        if not self.username:
            # Генерируем уникальный username из первых 6 символов UUID
            self.username = f"user{uuid.uuid4().hex[:6]}"
        # Нормализуем email к нижнему регистру
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        """Строковое представление пользователя."""
        return f"{self.username} ({self.role}, {'Активен' if self.is_active else 'Отключен'})"


class ConfirmationCode(models.Model):
    """
    Модель для хранения кодов подтверждения различных операций.
    
    Используется для подтверждения регистрации, смены пароля и email.
    Коды имеют ограниченное время жизни и автоматически генерируются.
    """
    
    REGISTRATION = 'registration'
    PASSWORD_CHANGE = 'password_change'
    EMAIL_CHANGE = 'email_change'
    CODE_TYPE_CHOICES = [
        (REGISTRATION, 'Регистрация'),
        (PASSWORD_CHANGE, 'Смена пароля'),
        (EMAIL_CHANGE, 'Смена email'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='confirmation_codes')
    code = models.CharField(max_length=6)
    code_type = models.CharField(max_length=20, choices=CODE_TYPE_CHOICES)
    target_email = models.EmailField(blank=True, null=True)  # Для смены email
    target_password = models.CharField(max_length=128, blank=True, null=True)  # Для смены пароля
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        """
        Переопределяет сохранение для автоматической установки времени истечения и генерации кода.
        
        Если expires_at не задан, устанавливает время истечения через 10 минут.
        Если code не задан, генерирует 6-значный случайный код.
        """
        if not self.expires_at:
            # Код действителен 10 минут по умолчанию
            self.expires_at = timezone.now() + datetime.timedelta(minutes=10)
        if not self.code:
            # Генерируем 6-значный код с ведущими нулями
            self.code = f"{random.randint(0, 999999):06d}"
        super().save(*args, **kwargs)

    def is_expired(self):
        """Проверяет, истёк ли срок действия кода."""
        return timezone.now() > self.expires_at

    def __str__(self):
        """Строковое представление кода подтверждения."""
        return f"{self.user.email} - {self.code_type} ({self.code})"
