from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from webpush import send_user_notification

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('achievement', 'Достижение'),
        ('system', 'Системное'),
        ('course', 'Курс'),
        ('streak', 'Серия дней'),
        ('level_up', 'Новый уровень'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Пользователь"
    )
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    message = models.TextField(verbose_name="Сообщение")
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default='system',
        verbose_name="Тип уведомления"
    )
    is_read = models.BooleanField(default=False, verbose_name="Прочитано")
    link = models.URLField(blank=True, null=True, verbose_name="Ссылка")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username}: {self.title}"

@receiver(post_save, sender=Notification)
def send_notification_realtime(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = f"user_notifications_{instance.user.id}"
        
        from .serializers import NotificationSerializer
        serializer = NotificationSerializer(instance)
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "send_notification",
                "notification": serializer.data
            }
        )

        payload = {
            "head": instance.title,
            "body": instance.message,
            "icon": "https://keisenpai.com/logo.png",
            "url": instance.link or "/notifications"
        }
        try:
            send_user_notification(user=instance.user, payload=payload, ttl=1000)
        except Exception as e:
            print(f"Webpush error: {e}")
