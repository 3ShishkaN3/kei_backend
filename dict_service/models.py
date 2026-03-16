from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
from course_service.models import Course
from lesson_service.models import Lesson

class DictionarySection(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='dictionary_sections',
        verbose_name="Курс"
    )
    title = models.CharField(max_length=200, verbose_name="Название раздела")
    banner_image = models.ImageField(
        upload_to='dict_section_banners/',
        null=True, blank=True,
        verbose_name="Баннер раздела (необязательно)"
    )
    is_primary = models.BooleanField(
        default=False,
        verbose_name="Основной раздел курса",
        help_text="Только один раздел может быть основным для курса."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_dictionary_sections',
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Кем создан"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Раздел словаря"
        verbose_name_plural = "Разделы словаря"
        ordering = ['course', '-is_primary', 'title']


    def __str__(self):
        primary_marker = " (Основной)" if self.is_primary else ""
        return f"{self.title} (Курс: {self.course.title}){primary_marker}"

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.is_primary:
            DictionarySection.objects.filter(course=self.course).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)

class DictionaryEntry(models.Model):
    section = models.ForeignKey(
        DictionarySection,
        on_delete=models.CASCADE,
        related_name='entries',
        verbose_name="Раздел словаря"
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='dictionary_entries',
        verbose_name="Урок (необязательно)"
    )
    term = models.CharField(max_length=200, db_index=True, verbose_name="Слово/Термин/Кандзи")
    reading = models.CharField(max_length=200, blank=True, null=True, db_index=True, verbose_name="Чтение (хирагана/катакана)")
    translation = models.TextField(blank=True, null=True, verbose_name="Перевод/Значение")
    pronunciation_audio = models.FileField(
        upload_to='dict_pronunciations/',
        null=True, blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg', 'm4a'])],
        verbose_name="Аудио произношения"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_dictionary_entries',
        on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Кем создано"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Словарная запись"
        verbose_name_plural = "Словарные записи"
        ordering = ['section', 'term', 'reading']

    def __str__(self):
        reading_part = f"({self.reading})" if self.reading else ""
        return f"{self.term}{reading_part} - {self.section.title}"

class UserLearnedEntry(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='learned_dictionary_entries',
        verbose_name="Пользователь"
    )
    entry = models.ForeignKey(
        DictionaryEntry,
        on_delete=models.CASCADE,
        related_name='learned_by_users',
        verbose_name="Словарная запись"
    )
    learned_at = models.DateTimeField(default=timezone.now, verbose_name="Дата изучения")

    class Meta:
        verbose_name = "Изученная запись"
        verbose_name_plural = "Изученные записи"
        unique_together = ('user', 'entry')
        ordering = ['user', '-learned_at']

    def __str__(self):
        return f"{self.user.username} изучил '{self.entry.term}'"

class KanjiCharacter(models.Model):
    character = models.CharField(max_length=50, unique=True, db_index=True)
    decomposition_tree = models.JSONField(default=dict, blank=True, verbose_name="Дерево декомпозиции")
    
    def __str__(self):
        return self.character

class KanjiStructure(models.Model):
    parent = models.ForeignKey(KanjiCharacter, related_name='components', on_delete=models.CASCADE)
    child = models.ForeignKey(KanjiCharacter, related_name='compounds', on_delete=models.CASCADE)
    
    class Meta:
        unique_together = ('parent', 'child')