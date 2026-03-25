from django.db import models
from django.conf import settings
from django.utils import timezone
from course_service.models import Course
from material_service.models import Test


class Exam(models.Model):
    """Экзамен по курсу. Создаётся преподавателем."""
    course = models.ForeignKey(
        Course,
        related_name='exams',
        on_delete=models.CASCADE,
        verbose_name="Курс"
    )
    title = models.CharField(max_length=255, verbose_name="Название экзамена")
    description = models.TextField(blank=True, verbose_name="Описание / Инструкция")
    duration_minutes = models.PositiveIntegerField(
        verbose_name="Длительность (минуты)",
        help_text="Сколько минут даётся на прохождение экзамена"
    )
    passing_score = models.DecimalField(
        max_digits=7, decimal_places=2,
        default=0.0,
        verbose_name="Проходной балл"
    )
    retake_interval_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="Интервал между попытками (минуты)",
        help_text="0 — без ограничений по времени."
    )
    is_published = models.BooleanField(default=False, verbose_name="Опубликован")
    require_camera = models.BooleanField(default=True, verbose_name="Требуется камера (прокторинг)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_exams',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Создатель"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Экзамен"
        verbose_name_plural = "Экзамены"
        ordering = ['course', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.course.title})"


class ExamSection(models.Model):
    """Секция экзамена. При переходе на следующую — возврат невозможен."""
    exam = models.ForeignKey(
        Exam,
        related_name='sections',
        on_delete=models.CASCADE,
        verbose_name="Экзамен"
    )
    title = models.CharField(max_length=255, verbose_name="Название секции")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Секция экзамена"
        verbose_name_plural = "Секции экзамена"
        ordering = ['exam', 'order']
        unique_together = ('exam', 'order')

    def __str__(self):
        return f"{self.title} (Экзамен: {self.exam.title}, #{self.order})"


class ExamSectionItem(models.Model):
    """Элемент секции — ссылка на существующий Test из material_service."""
    section = models.ForeignKey(
        ExamSection,
        related_name='items',
        on_delete=models.CASCADE,
        verbose_name="Секция"
    )
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='exam_items',
        verbose_name="Тест"
    )
    custom_max_score = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name="Кастомный максимальный балл",
        help_text="Если пусто, используется дефолтный балл (обычно 1.0)"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        verbose_name = "Элемент секции экзамена"
        verbose_name_plural = "Элементы секций экзамена"
        ordering = ['section', 'order']
        unique_together = ('section', 'order')

    def __str__(self):
        return f"Тест '{self.test.title}' в секции '{self.section.title}'"


class ExamAttempt(models.Model):
    """Попытка прохождения экзамена студентом. Одна попытка на студента."""
    STATUS_CHOICES = (
        ('in_progress', 'В процессе'),
        ('completed', 'Завершён'),
        ('timed_out', 'Время истекло'),
        ('terminated_by_proctoring', 'Прекращён (прокторинг)'),
    )

    exam = models.ForeignKey(
        Exam,
        related_name='attempts',
        on_delete=models.CASCADE,
        verbose_name="Экзамен"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='exam_attempts',
        on_delete=models.CASCADE,
        verbose_name="Студент"
    )
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='in_progress',
        verbose_name="Статус"
    )
    current_section_order = models.PositiveIntegerField(
        default=0,
        verbose_name="Текущая секция (order)"
    )
    started_at = models.DateTimeField(default=timezone.now, verbose_name="Начато")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершено")
    total_score = models.DecimalField(
        max_digits=7, decimal_places=2,
        null=True, blank=True,
        verbose_name="Итоговый балл"
    )
    max_possible_score = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Максимально возможный балл"
    )
    camera_violation_seconds = models.FloatField(
        default=0,
        verbose_name="Время нарушений камеры (сек)"
    )

    class Meta:
        verbose_name = "Попытка экзамена"
        verbose_name_plural = "Попытки экзаменов"

    def __str__(self):
        return f"{self.student.username} — {self.exam.title} ({self.get_status_display()})"

    @property
    def is_active(self):
        return self.status == 'in_progress'

    @property
    def deadline(self):
        """Дедлайн = started_at + duration_minutes."""
        if self.started_at and self.exam.duration_minutes:
            from datetime import timedelta
            return self.started_at + timedelta(minutes=self.exam.duration_minutes)
        return None

    @property
    def is_expired(self):
        dl = self.deadline
        if dl:
            return timezone.now() > dl
        return False


class ExamAnswer(models.Model):
    """Ответ студента на один элемент экзамена."""
    attempt = models.ForeignKey(
        ExamAttempt,
        related_name='answers',
        on_delete=models.CASCADE,
        verbose_name="Попытка"
    )
    exam_section_item = models.ForeignKey(
        ExamSectionItem,
        on_delete=models.CASCADE,
        verbose_name="Элемент секции"
    )
    answer_data = models.JSONField(
        default=dict,
        verbose_name="Данные ответа (JSON)",
        help_text="Формат зависит от типа теста"
    )
    submitted_file = models.FileField(
        upload_to='exam_answers/',
        null=True,
        blank=True,
        verbose_name="Прикрепленный файл"
    )
    score = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        verbose_name="Балл"
    )
    is_correct = models.BooleanField(
        null=True, blank=True,
        verbose_name="Правильно?"
    )
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="Отправлено")

    class Meta:
        verbose_name = "Ответ на экзамене"
        verbose_name_plural = "Ответы на экзамене"
        unique_together = ('attempt', 'exam_section_item')

    def __str__(self):
        return f"Ответ на '{self.exam_section_item.test.title}' (попытка {self.attempt_id})"
