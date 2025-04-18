from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone

class TextMaterial(models.Model):
    """Текстовый материал (статья, инструкция)."""
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
    """Изображение (фото, гиф, иллюстрация)."""
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

    class Meta:
        verbose_name = "Изображение"
        verbose_name_plural = "Изображения"

    def __str__(self):
        return self.title or f"Изображение #{self.id}"

class AudioMaterial(models.Model):
    """Аудио материал (произношение, диалог)."""
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

    class Meta:
        verbose_name = "Аудио материал"
        verbose_name_plural = "Аудио материалы"

    def __str__(self):
        return self.title or f"Аудио #{self.id}"

class VideoMaterial(models.Model):
    """Видео материал (урок, объяснение)."""
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
    """Документ (PDF, конспект, презентация)."""
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
    """Базовая модель для теста любого типа."""
    TEST_TYPE_CHOICES = (
        ('mcq-multi', 'Выбор нескольких ответов'),
        ('mcq-single', 'Выбор одного ответа'),
        ('free-text', 'Текстовый ответ'),
        ('word-order', 'Правильный порядок слов'),
        ('matching', 'Соотнесение'),
        ('pronunciation', 'Проверка произношения'),
        ('spelling', 'Проверка правописания'),
    )
    title = models.CharField(max_length=255, verbose_name="Название теста")
    description = models.TextField(blank=True, verbose_name="Описание/Инструкция к тесту")
    test_type = models.CharField(max_length=20, choices=TEST_TYPE_CHOICES, verbose_name="Тип теста")

    attached_image = models.ForeignKey(
        ImageMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tests_using_image', verbose_name="Прикрепленное изображение"
    )
    attached_audio = models.ForeignKey(
        AudioMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='tests_using_audio', verbose_name="Прикрепленное аудио"
    )

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
    """Вариант ответа для тестов типа MCQ."""
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
        return f"Опция для '{self.test.title}': {self.text}"

class FreeTextQuestion(models.Model):
    """Дополнительные данные для теста с текстовым ответом."""
    test = models.OneToOneField(
        Test,
        on_delete=models.CASCADE,
        related_name='free_text_question',
        limit_choices_to={'test_type': 'free-text'},
        verbose_name="Тест с текстовым ответом"
    )
    # Поле для правильного ответа (если проверка автоматическая) или эталона
    reference_answer = models.TextField(blank=True, null=True, verbose_name="Эталонный ответ (для сверки)")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение/Контекст к заданию")

    class Meta:
        verbose_name = "Вопрос с текстовым ответом"
        verbose_name_plural = "Вопросы с текстовым ответом"

    def __str__(self):
        return f"Вопрос для '{self.test.title}'"


class WordOrderSentence(models.Model):
    """Данные для теста на порядок слов."""
    test = models.OneToOneField( 
        Test,
        on_delete=models.CASCADE,
        related_name='word_order_sentence',
        limit_choices_to={'test_type': 'word-order'},
        verbose_name="Тест на порядок слов"
    )

    correct_order_words = models.JSONField(default=list, verbose_name="Слова в правильном порядке")
    distractor_words = models.JSONField(default=list, blank=True, verbose_name="Лишние слова (distractors)")
    display_prompt = models.CharField(max_length=500, blank=True, verbose_name="Подсказка/Начало предложения (необязательно)")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение к этой паре")

    class Meta:
        verbose_name = "Предложение для теста на порядок слов"
        verbose_name_plural = "Предложения для тестов на порядок слов"

    def __str__(self):
        return f"Порядок слов для '{self.test.title}'"


class MatchingPair(models.Model):
    """Одна пара для соотнесения в тесте."""
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='matching_pairs',
        limit_choices_to={'test_type': 'matching'},
        verbose_name="Тест на соотнесение"
    )
    prompt_text = models.CharField(max_length=500, blank=True, null=True, verbose_name="Текст для соотнесения")
    prompt_image = models.ForeignKey(
        ImageMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='matching_prompts', verbose_name="Изображение для соотнесения"
    )
    prompt_audio = models.ForeignKey(
        AudioMaterial, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='matching_prompts', verbose_name="Аудио для соотнесения"
    )
    correct_answer_text = models.CharField(max_length=500, verbose_name="Текст правильного 'облачка'")
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок отображения")
    explanation = models.TextField(blank=True, null=True, verbose_name="Пояснение к этой паре")

    class Meta:
        verbose_name = "Пара для соотнесения"
        verbose_name_plural = "Пары для соотнесения"
        ordering = ['test', 'order']

    def clean(self):
        # Проверка, что указан только один тип prompt
        prompts = [self.prompt_text, self.prompt_image, self.prompt_audio]
        if sum(p is not None and p != '' for p in prompts) != 1:
            raise ValidationError("Должен быть указан ровно один элемент для соотнесения (текст, изображение или аудио).")

    def __str__(self):
        return f"Пара для '{self.test.title}' (Ответ: {self.correct_answer_text})"


class MatchingDistractor(models.Model):
    """Лишнее 'облачко' для теста на соотнесение."""
    test = models.ForeignKey(
        Test,
        on_delete=models.CASCADE,
        related_name='matching_distractors',
        limit_choices_to={'test_type': 'matching'},
        verbose_name="Тест на соотнесение"
    )
    distractor_text = models.CharField(max_length=500, verbose_name="Текст лишнего 'облачка'")

    class Meta:
        verbose_name = "Лишнее облачко (соотнесение)"
        verbose_name_plural = "Лишние облачка (соотнесение)"

    def __str__(self):
        return f"Лишнее облачко для '{self.test.title}': {self.distractor_text}"


class PronunciationQuestion(models.Model):
    """Данные для теста на проверку произношения."""
    test = models.OneToOneField( # Один вопрос на тест
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
        return f"Произношение для '{self.test.title}'"

class SpellingQuestion(models.Model):
    """Данные для теста на проверку правописания."""
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
        return f"Правописание для '{self.test.title}'"


class TestSubmission(models.Model):
    """Запись об отправке теста студентом."""
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
        return f"Отправка '{self.test.title}' студентом {self.student.username} в {self.submitted_at}"
    
class MCQSubmissionAnswer(models.Model):
    """Выбранный вариант(ы) ответа для MCQ теста."""
    submission = models.ForeignKey(TestSubmission, on_delete=models.CASCADE, related_name='mcq_answers')
    # Используем ManyToManyField для связи с выбранными опциями
    selected_options = models.ManyToManyField(
        MCQOption,
        related_name='submissions_selected_in',
        verbose_name="Выбранные варианты"
    )


    class Meta:
        verbose_name = "Ответ на MCQ"
        verbose_name_plural = "Ответы на MCQ"

class FreeTextSubmissionAnswer(models.Model):
    """Отправленный текстовый ответ."""
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='free_text_answer')
    answer_text = models.TextField(verbose_name="Текст ответа студента")

    class Meta:
        verbose_name = "Ответ текстом"
        verbose_name_plural = "Ответы текстом"

class WordOrderSubmissionAnswer(models.Model):
    """Отправленный порядок слов."""
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='word_order_answer')
    submitted_order_words = models.JSONField(default=list, verbose_name="Отправленный порядок слов (JSON)")

    class Meta:
        verbose_name = "Ответ на порядок слов"
        verbose_name_plural = "Ответы на порядок слов"


class MatchingSubmissionAnswer(models.Model):
    """Отправленное соотнесение для одной пары."""
    submission = models.ForeignKey(TestSubmission, on_delete=models.CASCADE, related_name='matching_answers')
    matching_pair = models.ForeignKey(MatchingPair, on_delete=models.CASCADE, verbose_name="Пара (задание)")
    submitted_answer_text = models.CharField(max_length=500, verbose_name="Соотнесенное 'облачко' (ответ студента)")

    class Meta:
        verbose_name = "Ответ на соотнесение"
        verbose_name_plural = "Ответы на соотнесение"
        unique_together = ('submission', 'matching_pair') # Один ответ на пару в рамках одной отправки

class PronunciationSubmissionAnswer(models.Model):
    """Отправленное аудио для проверки произношения."""
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='pronunciation_answer')
    submitted_audio_file = models.FileField(
        upload_to='submission_pronunciation/',
        validators=[FileExtensionValidator(allowed_extensions=['mp3', 'wav', 'ogg', 'm4a'])], # Пример
        verbose_name="Запись произношения студента"
    )

    class Meta:
        verbose_name = "Ответ на произношение"
        verbose_name_plural = "Ответы на произношение"

class SpellingSubmissionAnswer(models.Model):
    """Отправленное изображение для проверки правописания."""
    submission = models.OneToOneField(TestSubmission, on_delete=models.CASCADE, related_name='spelling_answer')
    submitted_image_file = models.ImageField(
        upload_to='submission_spelling/',
        verbose_name="Фото написания студента"
    )

    class Meta:
        verbose_name = "Ответ на правописание"
        verbose_name_plural = "Ответы на правописание"
