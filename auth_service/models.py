import datetime
import random
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid

class User(AbstractUser):
    class Role(models.TextChoices):
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
        if not self.username:
            self.username = f"user{uuid.uuid4().hex[:6]}"
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role}, {'Активен' if self.is_active else 'Отключен'})"

class ConfirmationCode(models.Model):
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
    target_email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + datetime.timedelta(minutes=10)
        if not self.code:
            self.code = f"{random.randint(0, 999999):06d}"
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.user.email} - {self.code_type} ({self.code})"