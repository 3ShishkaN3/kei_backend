from django.db import models
from django.conf import settings
from django.utils import timezone


class UserKnowledgeProfile(models.Model):
    """
    Кешированный профиль знаний ученика для конкретного курса.
    Обновляется инкрементально: при каждом анализе скармливаем нейронке
    только данные, обновлённые после last_analyzed_at.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='knowledge_profiles',
        verbose_name='Ученик'
    )
    course = models.ForeignKey(
        'course_service.Course',
        on_delete=models.CASCADE,
        related_name='knowledge_profiles',
        verbose_name='Курс'
    )
    profile_data = models.JSONField(
        default=dict,
        verbose_name='Данные профиля (JSON)',
        help_text='Сильные/слабые стороны, темы для повторения, рекомендации'
    )
    last_analyzed_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Последний анализ'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Профиль знаний'
        verbose_name_plural = 'Профили знаний'
        unique_together = ('user', 'course')

    def __str__(self):
        return f'Профиль знаний: {self.user.username} — {self.course}'


class DailyChallenge(models.Model):
    """
    Ежедневное испытание. Одно на пользователя + курс + день.
    """
    GENERATION_STATUS_CHOICES = (
        ('pending', 'Ожидает генерации'),
        ('generating', 'Генерируется'),
        ('ready', 'Готово'),
        ('failed', 'Ошибка генерации'),
    )
    COMPLETION_STATUS_CHOICES = (
        ('not_started', 'Не начато'),
        ('in_progress', 'В процессе'),
        ('completed', 'Завершено'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='daily_challenges',
        verbose_name='Ученик'
    )
    course = models.ForeignKey(
        'course_service.Course',
        on_delete=models.CASCADE,
        related_name='daily_challenges',
        verbose_name='Курс'
    )
    date = models.DateField(
        verbose_name='Дата испытания',
        help_text='Дата по МСК'
    )

    generation_status = models.CharField(
        max_length=20,
        choices=GENERATION_STATUS_CHOICES,
        default='pending',
        verbose_name='Статус генерации'
    )
    completion_status = models.CharField(
        max_length=20,
        choices=COMPLETION_STATUS_CHOICES,
        default='not_started',
        verbose_name='Статус прохождения'
    )

    celery_task_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='ID Celery-задачи'
    )

    score = models.PositiveIntegerField(
        default=0,
        verbose_name='Набранные очки'
    )
    total_items = models.PositiveIntegerField(
        default=0,
        verbose_name='Всего заданий'
    )
    correct_items = models.PositiveIntegerField(
        default=0,
        verbose_name='Правильных ответов'
    )
    coins_awarded = models.PositiveIntegerField(
        default=0,
        verbose_name='Начислено монет'
    )

    media_placeholders = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Слоты для медиа (будущая генерация)',
        help_text='Промпты для генерации картинок/аудио. Заполняются нейронкой.'
    )

    blitz_quizzes = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Блиц-тесты (JSON)'
    )

    generation_error = models.TextField(
        blank=True,
        default='',
        verbose_name='Ошибка генерации'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Дата завершения'
    )

    class Meta:
        verbose_name = 'Ежедневное испытание'
        verbose_name_plural = 'Ежедневные испытания'
        unique_together = ('user', 'course', 'date')
        ordering = ['-date']

    def __str__(self):
        return f'{self.user.username} — {self.date} ({self.get_generation_status_display()})'

    @property
    def is_expired(self):
        """Проверяет, истекло ли испытание (прошла полночь по МСК)."""
        from datetime import datetime
        import pytz
        msk = pytz.timezone('Europe/Moscow')
        now_msk = datetime.now(msk).date()
        return self.date < now_msk

    def is_stale_generating(self, timeout_minutes=5):
        """Проверяет, зависла ли генерация (>timeout_minutes без обновления)."""
        if self.generation_status != 'generating':
            return False
        return (timezone.now() - self.updated_at).total_seconds() > timeout_minutes * 60


class ChallengeTest(models.Model):
    """
    Связь между DailyChallenge и Test (из material_service).
    Celery-задача создаёт реальные Test-объекты и линкует их сюда.
    """
    challenge = models.ForeignKey(
        DailyChallenge,
        on_delete=models.CASCADE,
        related_name='challenge_tests',
        verbose_name='Испытание'
    )
    test = models.ForeignKey(
        'material_service.Test',
        on_delete=models.CASCADE,
        related_name='challenge_links',
        verbose_name='Тест'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок'
    )

    class Meta:
        verbose_name = 'Тест испытания'
        verbose_name_plural = 'Тесты испытаний'
        ordering = ['challenge', 'order']
        unique_together = ('challenge', 'test')

    def __str__(self):
        return f'Тест #{self.order} — {self.challenge}'
