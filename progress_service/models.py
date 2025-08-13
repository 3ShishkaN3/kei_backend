from django.db import models
from django.conf import settings
from django.utils import timezone
from course_service.models import Course
from lesson_service.models import Lesson, Section


class UserProgress(models.Model):
    """Общий прогресс пользователя"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='progress',
        verbose_name="Пользователь"
    )
    total_courses_enrolled = models.PositiveIntegerField(default=0, verbose_name="Всего записей на курсы")
    total_courses_completed = models.PositiveIntegerField(default=0, verbose_name="Всего завершенных курсов")
    total_lessons_completed = models.PositiveIntegerField(default=0, verbose_name="Всего завершенных уроков")
    total_sections_completed = models.PositiveIntegerField(default=0, verbose_name="Всего завершенных разделов")
    total_tests_passed = models.PositiveIntegerField(default=0, verbose_name="Всего пройденных тестов")
    total_tests_failed = models.PositiveIntegerField(default=0, verbose_name="Всего проваленных тестов")
    total_learning_time_minutes = models.PositiveIntegerField(default=0, verbose_name="Общее время обучения (минуты)")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Прогресс пользователя"
        verbose_name_plural = "Прогресс пользователей"

    def __str__(self):
        return f"Прогресс {self.user.username}"


class CourseProgress(models.Model):
    """Прогресс по курсу"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='course_progress',
        verbose_name="Пользователь"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='user_progress',
        verbose_name="Курс"
    )
    total_lessons = models.PositiveIntegerField(default=0, verbose_name="Всего уроков в курсе")
    completed_lessons = models.PositiveIntegerField(default=0, verbose_name="Завершенных уроков")
    total_sections = models.PositiveIntegerField(default=0, verbose_name="Всего разделов в курсе")
    completed_sections = models.PositiveIntegerField(default=0, verbose_name="Завершенных разделов")
    total_tests = models.PositiveIntegerField(default=0, verbose_name="Всего тестов в курсе")
    passed_tests = models.PositiveIntegerField(default=0, verbose_name="Пройденных тестов")
    failed_tests = models.PositiveIntegerField(default=0, verbose_name="Проваленных тестов")
    completion_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00, 
        verbose_name="Процент завершения"
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата начала")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Прогресс по курсу"
        verbose_name_plural = "Прогресс по курсам"
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.username} - {self.course.title} ({self.completion_percentage}%)"


class LessonProgress(models.Model):
    """Прогресс по уроку"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lesson_progress',
        verbose_name="Пользователь"
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='user_progress',
        verbose_name="Урок"
    )
    total_sections = models.PositiveIntegerField(default=0, verbose_name="Всего разделов в уроке")
    completed_sections = models.PositiveIntegerField(default=0, verbose_name="Завершенных разделов")
    total_tests = models.PositiveIntegerField(default=0, verbose_name="Всего тестов в уроке")
    passed_tests = models.PositiveIntegerField(default=0, verbose_name="Пройденных тестов")
    failed_tests = models.PositiveIntegerField(default=0, verbose_name="Проваленных тестов")
    completion_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00, 
        verbose_name="Процент завершения"
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата начала")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Прогресс по уроку"
        verbose_name_plural = "Прогресс по урокам"
        unique_together = ('user', 'lesson')

    def __str__(self):
        return f"{self.user.username} - {self.lesson.title} ({self.completion_percentage}%)"


class SectionProgress(models.Model):
    """Прогресс по секциям"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='section_progress',
        verbose_name="Пользователь"
    )
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='user_progress',
        verbose_name="Секция"
    )
    total_items = models.PositiveIntegerField(default=0, verbose_name="Всего элементов в секции")
    completed_items = models.PositiveIntegerField(default=0, verbose_name="Завершенных элементов")
    total_tests = models.PositiveIntegerField(default=0, verbose_name="Всего тестов в секции")
    passed_tests = models.PositiveIntegerField(default=0, verbose_name="Пройденных тестов")
    failed_tests = models.PositiveIntegerField(default=0, verbose_name="Проваленных тестов")
    completion_percentage = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=0.00, 
        verbose_name="Процент завершения"
    )
    is_visited = models.BooleanField(default=False, verbose_name="Посещена")
    visited_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата посещения")
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата начала")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name="Последняя активность")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Прогресс по секции"
        verbose_name_plural = "Прогресс по секциям"
        unique_together = ('user', 'section')

    def __str__(self):
        return f"{self.user.username} - {self.section.title} ({self.completion_percentage}%)"


class TestProgress(models.Model):
    """Прогресс по тестам"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='test_progress',
        verbose_name="Пользователь"
    )
    test_id = models.PositiveIntegerField(verbose_name="ID теста")
    test_title = models.CharField(max_length=255, verbose_name="Название теста")
    test_type = models.CharField(max_length=50, verbose_name="Тип теста")
    section_id = models.PositiveIntegerField(verbose_name="ID раздела")
    lesson_id = models.PositiveIntegerField(verbose_name="ID урока")
    course_id = models.PositiveIntegerField(verbose_name="ID курса")
    attempts_count = models.PositiveIntegerField(default=0, verbose_name="Количество попыток")
    best_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        verbose_name="Лучший результат"
    )
    last_score = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        verbose_name="Последний результат"
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('not_started', 'Не начат'),
            ('in_progress', 'В процессе'),
            ('passed', 'Пройден'),
            ('failed', 'Провален'),
        ],
        default='not_started',
        verbose_name="Статус"
    )
    first_attempt_at = models.DateTimeField(null=True, blank=True, verbose_name="Первая попытка")
    last_attempt_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя попытка")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Прогресс по тесту"
        verbose_name_plural = "Прогресс по тестам"
        unique_together = ('user', 'test_id')

    def __str__(self):
        return f"{self.user.username} - {self.test_title} ({self.status})"


class LearningStats(models.Model):
    """Статистика обучения"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learning_stats',
        verbose_name="Пользователь"
    )
    total_study_days = models.PositiveIntegerField(default=0, verbose_name="Всего дней обучения")
    current_streak_days = models.PositiveIntegerField(default=0, verbose_name="Текущая серия дней")
    longest_streak_days = models.PositiveIntegerField(default=0, verbose_name="Самая длинная серия дней")
    average_daily_time_minutes = models.PositiveIntegerField(default=0, verbose_name="Среднее время в день (минуты)")
    total_achievements = models.PositiveIntegerField(default=0, verbose_name="Всего достижений")
    level = models.PositiveIntegerField(default=1, verbose_name="Уровень")
    experience_points = models.PositiveIntegerField(default=0, verbose_name="Очки опыта")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Статистика обучения"
        verbose_name_plural = "Статистика обучения"

    def __str__(self):
        return f"Статистика {self.user.username} (Уровень {self.level})"
