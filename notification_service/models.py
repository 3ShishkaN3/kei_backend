from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Notification(models.Model):
    data = models.JSONField(null=True, blank=True, verbose_name='Data')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications', verbose_name='Получатель')
# Create your models here.
    class NotificationType(models.TextChoices):
        NEW_LESSON_AVAILABLE = 'NEW_LESSON_AVAILABLE', 'Новый урок доступен'
    type = models.CharField(max_length = 50, choices = NotificationType.choices, verbose_name='Тип')

    is_read = models.BooleanField(default= False, verbose_name='Прочитано?')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата и время')
    class Meta:
        verbose_name = _('Уведомление')
        verbose_name_plural = _('Уведомления')
        ordering = ['-created_at']

    def __str__(self):
        return f'Уведомление для {self.recipient} ({self.get_type_display()})'