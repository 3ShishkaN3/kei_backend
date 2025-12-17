from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class Notification(models.Model):
    data = models.JSONField(null=True, blank=True, verbose_name='Data')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications', verbose_name='Получатель')

    class NotificationType(models.TextChoices):
        # Для ученика
        NEW_LESSON_AVAILABLE = 'NEW_LESSON_AVAILABLE', 'Новый урок доступен'
        NEW_MATERIAL_IN_COURSE = 'NEW_MATERIAL_IN_COURSE', 'Новый материал в курсе'
        TEST_GRADED = 'TEST_GRADED', 'Тест проверен'
        COURSE_COMPLETED = 'COURSE_COMPLETED', 'Курс пройден'

        # Для учителя
        STUDENT_ENROLLED = 'STUDENT_ENROLLED', 'Новый ученик на курсе'
        SUBMISSION_REQUIRES_GRADING = 'SUBMISSION_REQUIRES_GRADING', 'Тест требует проверки'
    type = models.CharField(max_length = 50, choices = NotificationType.choices, verbose_name='Тип')

    is_read = models.BooleanField(default= False, verbose_name='Прочитано?')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата и время')
    class Meta:
        verbose_name = _('Уведомление')
        verbose_name_plural = _('Уведомления')
        ordering = ['-created_at']

    def __str__(self):
        return f'Уведомление для {self.recipient} ({self.get_type_display()})'