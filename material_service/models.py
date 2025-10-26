from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone

class TextMaterial(models.Model):
    title = models.CharField(max_length=255, blank=True, verbose_name="Заголовок (необязательно)")
    content = models.TextField(verbose_name="Содержимое (текст или Markdown)")
    is_markdown = models.BooleanField(default=False, verbose_name="Использовать Markdown")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_text_materials',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Текстовый материал"
        verbose_name_plural = "Текстовые материалы"

    def __str__(self):
        return self.title or f"Текст #{self.id}"

class ImageMaterial(models.Model):
    title = models.CharField(max_length=255, blank=True, verbose_name="Заголовок (необязательно)")
    alt_text = models.CharField(max_length=255, blank=True, verbose_name="Alt текст (для доступности)")
    image = models.ImageField(
        upload_to='material_images/',
        verbose_name="Файл изображения"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_image_materials',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_file_field_name(cls):
        return 'image'

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"

    def __str__(self):
        return self.title or f"Изображение #{self.id}"

class AudioMaterial(models.Model):
    title = models.CharField(max_length=255, blank=True, verbose_name="Заголовок (необязательно)")
    audio_file = models.FileField(
        upload_to='material_audio/',
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg', 'm4a'])], 
        verbose_name="Аудио файл"
    )
    transcript = models.TextField(blank=True, null=True, verbose_name="Транскрипция (необязательно)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_audio_materials',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get_file_field_name(cls):
        return 'audio_file'

    class Meta:
        verbose_name = "Аудио материал"
        verbose_name_plural = "Аудио материалы"

    def __str__(self):
        return self.title or f"Аудио #{self.id}"

class VideoMaterial(models.Model):
    VIDEO_SOURCE_CHOICES = (
        ('url', 'URL (YouTube, Vimeo, etc.)'),
        ('file', 'Загруженный файл'),
    )
    title = models.CharField(max_length=255, blank=True, verbose_name="Заголовок (необязательно)")
    source_type = models.CharField(max_length=10, choices=VIDEO_SOURCE_CHOICES, default='url', verbose_name="Источник видео")
    video_url = models.URLField(blank=True, null=True, verbose_name="URL видео (если источник URL)")
    video_file = models.FileField(
        upload_to='material_video/',
        blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['mp4', 'mov', 'avi', 'wmv'])],
        verbose_name="Видео файл (если источник файл)"
    )
    transcript = models.TextField(blank=True, null=True, verbose_name="Транскрипция (необязательно)")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_video_materials',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Видео материал"
        verbose_name_plural = "Видео материалы"

    def clean(self):
        if self.source_type == 'url' and not self.video_url:
            raise ValidationError({'video_url': 'Укажите URL видео.'})
        if self.source_type == 'file' and not self.video_file:
            raise ValidationError({'video_file': 'Загрузите видео файл.'})
        if self.source_type == 'url':
            self.video_file = None
        if self.source_type == 'file':
            self.video_url = None 

    def __str__(self):
        return self.title or f"Видео #{self.id}"

class DocumentMaterial(models.Model):
    title = models.CharField(max_length=255, blank=True, verbose_name="Заголовок (необязательно)")
    document_file = models.FileField(
        upload_to='material_docs/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'ppt', 'pptx', 'doc', 'docx'])],
        verbose_name="Файл документа"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_document_materials',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"

    def __str__(self):
        return self.title or f"Документ #{self.id}"


class Test(models.Model):
    TEST_TYPE_CHOICES = (
        ('mcq-multi', 'Выбор нескольких ответов'),
        ('mcq-single', 'Выбор одного ответа'),
        ('free-text', 'Текстовый ответ'),
        ('word-order', 'Правильный порядок слов (в строке)'),
        ('drag-and-drop', 'Перетаскивание элементов (облачка и ячейки)'),
        ('pronunciation', 'Проверка произношения'),
        ('spelling', 'Проверка правописания'),
    )
    title = models.CharField(max_length=255, verbose_name="Название теста")
    description = models.TextField(blank=True, verbose_name="Описание/Инструкция к тесту")
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, verbose_name="Тип теста")

    attached_image = models.ForeignKey(
        ImageMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tests_using_image', verbose_name="Прикрепленное изображение к тесту (общее)"
    )
    attached_audio = models.ForeignKey(
        AudioMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tests_using_audio', verbose_name="Прикрепленное аудио к тесту (общее)"
    )
    
    draggable_options_pool = models.JSONField(default=list, blank=True, verbose_name="Набор всех облачков (вариантов)")
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_tests',
        on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Тест"
        verbose_name_plural = "Тесты"

    def __str__(self):
        return f"{self.title} ({self.get_test_type_display()})"


class MCQOption(models.Model):
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='mcq_options',
        limit_choices_to={'test_type__in': ['mcq-single', 'mcq-multi']},
        verbose_name="Тест MCQ"
    )
    text = models.CharField(max_length=500, verbose_name="Текст варианта ответа")
    is_correct = models.BooleanField(default=False, verbose_name="Правильный ответ?")
    feedback = models.TextField(blank=True, null=True, verbose_name="Пояснение (если ответ неверный/верный)")
    explanation = models.TextField(blank=True, null=True, verbose_name="Общее пояснение к варианту (всегда видно после)")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок отображения")

    class Meta:
        verbose_name = "Вариант ответа MCQ"
        verbose_name_plural = "Варианты ответов MCQ"
        ordering = ['test', 'order']

    def __str__(self):
        return f"{self.text} (Тест: {self.test.title})"

class FreeTextQuestion(models.Model):
    test = models.OneToOneField(
        Test,
        on_delete=models.CASCADE,
        related_name='free_text_question',
        limit_choices_to={'test_type': 'free-text'},
        verbose_name="Тест с текстовым ответом"
    )
    reference_answer = models.TextField(blank=True, null=True, verbose_name="Эталонный ответ (для сверки)")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение/Контекст к заданию")

    class Meta:
        verbose_name = "Вопрос с текстовым ответом"
        verbose_name_plural = "Вопросы с текстовым ответом"

    def __str__(self):
        return f"Текстовый вопрос для теста: {self.test.title}"

class WordOrderSentence(models.Model):
    test = models.OneToOneField( 
        Test,
        on_delete=models.CASCADE,
        related_name='word_order_sentence_details',
        limit_choices_to={'test_type': 'word_order'},
        verbose_name="Задание на порядок слов"
    )
    correct_ordered_texts = models.JSONField(
        default=list, 
        verbose_name="Тексты в правильном порядке (из пула облачков)"
    )
    display_prompt = models.CharField(
        max_length=500, blank=True, 
        verbose_name="Подсказка/Начало предложения (необязательно)"
    )
    explanation = models.TextField(
        blank=True, null=True, 
        verbose_name="Пояснение к заданию"
    )

    class Meta:
        verbose_name = "Задание на порядок слов (из пула)"
        verbose_name_plural = "Задания на порядок слов (из пула)"

    def __str__(self):
        return f"Порядок слов для теста: {self.test.title}"

class MatchingPair(models.Model):
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='drag_drop_slots',
        limit_choices_to={'test_type': 'drag-and-drop'},
        verbose_name="Тест (Перетаскивание)"
    )
    prompt_text = models.CharField(max_length=500, blank=True, null=True, verbose_name="Текст-задание для ячейки (если есть)")
    prompt_image = models.ForeignKey(
        ImageMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='drag_drop_slot_images', verbose_name="Изображение-задание для ячейки"
    )
    prompt_audio = models.ForeignKey(
        AudioMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='drag_drop_slot_audio', verbose_name="Аудио-задание для ячейки"
    )
    
    correct_answer_text = models.CharField(max_length=500, verbose_name="Текст правильного облачка для этой ячейки")
    
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок отображения ячейки")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение к этой ячейке/ответу")

    class Meta:
        verbose_name = "Ячейка для перетаскивания (слот)"
        verbose_name_plural = "Ячейки для перетаскивания (слоты)"
        ordering = ['test', 'order']

    def __str__(self):
        return f"Ячейка {self.order} для теста: {self.test.title}"

class PronunciationQuestion(models.Model):
    test = models.OneToOneField(
        Test,
        on_delete=models.CASCADE,
        related_name='pronunciation_question',
        limit_choices_to={'test_type': 'pronunciation'},
        verbose_name="Тест на произношение"
    )

    text_to_pronounce = models.TextField(blank=True, null=True, verbose_name="Текст для произношения (если есть)")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение/Контекст к заданию")

    class Meta:
        verbose_name = "Вопрос на произношение"
        verbose_name_plural = "Вопросы на произношение"

    def __str__(self):
        return f"Вопрос на произношение для теста: {self.test.title}"

class SpellingQuestion(models.Model):
    test = models.OneToOneField( 
        Test,
        on_delete=models.CASCADE,
        related_name='spelling_question',
        limit_choices_to={'test_type': 'spelling'},
        verbose_name="Тест на правописание"
    )
    reference_spelling = models.TextField(blank=True, null=True, verbose_name="Эталонное написание (для сверки)")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение/Контекст к заданию")

    class Meta:
        verbose_name = "Вопрос на правописание"
        verbose_name_plural = "Вопросы на правописание"

    def __str__(self):
        return f"Вопрос на правописание для теста: {self.test.title}"

class TestSubmission(models.Model):
    SUBMISSION_STATUS_CHOICES = (
        ('submitted', 'Отправлено (ожидает автопроверки/отправки на проверку)'),
        ('grading_pending', 'На проверке'),
        ('graded', 'Проверено'),
        ('auto_failed', 'Автопроверка: Не пройдено'),
        ('auto_passed', 'Автопроверка: Пройдено'),
    )

    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='submissions', verbose_name="Тест")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='test_submissions',
        verbose_name="Студент"
    )


    section_item = models.ForeignKey(
        'lesson_service.SectionItem',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='test_submissions',
        verbose_name="Элемент раздела (контекст)"
    )
    submitted_at = models.DateTimeField(default=timezone.now, verbose_name="Время отправки")
    status = models.CharField(
        max_length=20,
        choices=SUBMISSION_STATUS_CHOICES,
        default='submitted',
        verbose_name="Статус отправки"
    )

    score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Оценка (если применимо)"
    )
    feedback = models.TextField(blank=True, null=True, verbose_name="Обратная связь от проверяющего")

    class Meta:
        verbose_name = "Отправка теста"
        verbose_name_plural = "Отправки тестов"
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.student.username} - {self.test.title} ({self.get_status_display()})"

class MCQSubmissionAnswer(models.Model):
    submission = models.ForeignKey(TestSubmission, on_delete=models.CASCADE, related_name='mcq_answers')
    selected_options = models.ManyToManyField(
        MCQOption,
        verbose_name="Выбранные варианты ответов"
    )

    class Meta:
        verbose_name = "Ответ на MCQ"
        verbose_name_plural = "Ответы на MCQ"

class FreeTextSubmissionAnswer(models.Model):
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='free_text_answer')
    answer_text = models.TextField(verbose_name="Текст ответа студента")

    class Meta:
        verbose_name = "Ответ текстом"
        verbose_name_plural = "Ответы текстом"

class WordOrderSubmissionAnswer(models.Model):
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='word_order_answer')
    submitted_order_words = models.JSONField(default=list, verbose_name="Отправленный порядок слов (JSON)")

    class Meta:
        verbose_name = "Ответ на порядок слов"
        verbose_name_plural = "Ответы на порядок слов"

class DragDropSubmissionAnswer(models.Model):
    submission = models.ForeignKey(TestSubmission, on_delete=models.CASCADE, related_name='drag_drop_answers')
    slot = models.ForeignKey(MatchingPair, on_delete=models.CASCADE, verbose_name="Ячейка (слот)")
    dropped_option_text = models.CharField(max_length=500, verbose_name="Текст перетащенного облачка")
    is_correct = models.BooleanField(null=True, blank=True, verbose_name="Ответ правильный?")

    class Meta:
        verbose_name = "Ответ на перетаскивание в ячейку"
        verbose_name_plural = "Ответы на перетаскивание в ячейки"
        unique_together = ('submission', 'slot') 

class MatchingSubmissionAnswer(models.Model):
    submission = models.ForeignKey(TestSubmission, on_delete=models.CASCADE, related_name='matching_answers')
    matching_pair = models.ForeignKey(MatchingPair, on_delete=models.CASCADE, verbose_name="Пара (задание)")
    submitted_answer_text = models.CharField(max_length=500, verbose_name="Соотнесенное 'облачко' (ответ студента)")

    class Meta:
        verbose_name = "Ответ на соотнесение"
        verbose_name_plural = "Ответы на соотнесение"
        unique_together = ('submission', 'matching_pair')

class PronunciationSubmissionAnswer(models.Model):
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='pronunciation_answer')
    submitted_audio_file = models.FileField(
        upload_to='test_pronunciation_answers/',
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg', 'm4a'])],
        verbose_name="Аудио ответ студента"
    )

    class Meta:
        verbose_name = "Ответ на произношение"
        verbose_name_plural = "Ответы на произношение"

class SpellingSubmissionAnswer(models.Model):
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='spelling_answer')
    submitted_image_file = models.ImageField(
        upload_to='test_spelling_answers/',
        verbose_name="Изображение с написанным ответом"
    )

    class Meta:
        verbose_name = "Ответ на правописание"
        verbose_name_plural = "Ответы на правописание"