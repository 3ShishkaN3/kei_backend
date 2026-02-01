from django.db import models
from django.conf import settings
from course_service.models import Course
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class Lesson(models.Model):
    course = models.ForeignKey(
        Course,
        related_name='lessons',
        on_delete=models.CASCADE,
        verbose_name="Курс"
    )
    title = models.CharField(max_length=255, verbose_name="Название урока")
    cover_image = models.ImageField(
        upload_to='lesson_covers/',
        null=True,
        blank=True,
        verbose_name="Обложка урока"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_lessons',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Кем создан"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок в курсе",
        help_text="Определяет ручной порядок отображения уроков внутри курса"
    )
    table_of_contents = models.TextField(
        blank=True,
        null=True,
        verbose_name="Оглавление",
        help_text="Опциональное оглавление или краткое описание содержания урока"
    )

    class Meta:
        verbose_name = "Урок"
        verbose_name_plural = "Уроки"
        ordering = ['course', 'order', 'id']
        unique_together = ('course', 'order')

    def __str__(self):
        return f"{self.title} (Курс: {self.course.title})"

class Section(models.Model):
    lesson = models.ForeignKey(
        Lesson,
        related_name='sections',
        on_delete=models.CASCADE,
        verbose_name="Урок"
    )
    title = models.CharField(max_length=255, verbose_name="Название раздела")
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок",
        help_text="Порядок отображения раздела в уроке"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Раздел урока"
        verbose_name_plural = "Разделы уроков"
        ordering = ['lesson', 'order']
        unique_together = ('lesson', 'order')

    def __str__(self):
        return f"{self.title} (Урок: {self.lesson.title}, Порядок: {self.order})"

class SectionCompletion(models.Model):
    section = models.ForeignKey(
        Section,
        related_name='completions',
        on_delete=models.CASCADE,
        verbose_name="Раздел"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='section_completions',
        on_delete=models.CASCADE,
        verbose_name="Ученик"
    )
    completed_at = models.DateTimeField(default=timezone.now, verbose_name="Дата завершения")

    class Meta:
        verbose_name = "Завершение раздела"
        verbose_name_plural = "Завершения разделов"
        unique_together = ('section', 'student')

    def __str__(self):
        return f"{self.student.username} завершил раздел {self.section.title}"

class LessonCompletion(models.Model):
    lesson = models.ForeignKey(
        Lesson,
        related_name='completions',
        on_delete=models.CASCADE,
        verbose_name="Урок"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='lesson_completions',
        on_delete=models.CASCADE,
        verbose_name="Ученик"
    )
    completed_at = models.DateTimeField(default=timezone.now, verbose_name="Дата завершения")

    class Meta:
        verbose_name = "Завершение урока"
        verbose_name_plural = "Завершения уроков"
        unique_together = ('lesson', 'student')

    def __str__(self):
        return f"{self.student.username} завершил урок {self.lesson.title}"

  
class SectionItem(models.Model):
    ITEM_TYPE_CHOICES = (
        ('text', 'Текст'),
        ('image', 'Изображение'),
        ('audio', 'Аудио'),
        ('video', 'Видео'),
        ('document', 'Документ/Презентация'),
        ('test', 'Тест'),
    )

    section = models.ForeignKey(
        Section,
        related_name='items',
        on_delete=models.CASCADE,
        verbose_name="Раздел"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок в разделе",
        help_text="Порядок отображения элемента в разделе"
    )
    item_type = models.CharField(
        max_length=20,
        choices=ITEM_TYPE_CHOICES,
        verbose_name="Тип элемента"
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Тип контента",
        limit_choices_to={'app_label': 'material_service'}
    )
    object_id = models.PositiveIntegerField(
        verbose_name="ID объекта контента"
    )
    content_object = GenericForeignKey('content_type', 'object_id')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Элемент раздела"
        verbose_name_plural = "Элементы разделов"
        ordering = ['section', 'order']
        unique_together = ('section', 'order')

    def __str__(self):
        return f"Элемент {self.get_item_type_display()} (Порядок: {self.order}) в разделе '{self.section.title}'"
