from rest_framework import serializers
from .models import (
    TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial,
    Test, MCQOption, FreeTextQuestion, WordOrderSentence, MatchingPair, MatchingDistractor,
    PronunciationQuestion, SpellingQuestion,
    TestSubmission, MCQSubmissionAnswer, FreeTextSubmissionAnswer, WordOrderSubmissionAnswer,
    MatchingSubmissionAnswer, PronunciationSubmissionAnswer, SpellingSubmissionAnswer
)

from django.db import transaction

from auth_service.serializers import UserSerializer


class TextMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextMaterial
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

class ImageMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageMaterial
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

class AudioMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = AudioMaterial
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

class VideoMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoMaterial
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

class DocumentMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentMaterial
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

# --- Сериализаторы для CRUD тестов и их компонентов ---

class MCQOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MCQOption
        fields = ['id', 'text', 'is_correct', 'feedback', 'explanation', 'order']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}

class MatchingPairSerializer(serializers.ModelSerializer):
    prompt_image = ImageMaterialSerializer(read_only=True)
    prompt_audio = AudioMaterialSerializer(read_only=True)
    class Meta:
        model = MatchingPair
        fields = [
            'id', 'prompt_text', 'prompt_image', 'prompt_audio',
            'correct_answer_text', 'explanation', 'order'
        ]
        extra_kwargs = {'test': {'read_only': True, 'required': False}}


class MatchingDistractorSerializer(serializers.ModelSerializer):
     class Meta:
        model = MatchingDistractor
        fields = ['id', 'distractor_text']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}


# Добавляем сериализаторы для других компонентов (даже если они простые)
class FreeTextQuestionSerializer(serializers.ModelSerializer):
     class Meta:
        model = FreeTextQuestion
        fields = ['id', 'reference_answer', 'explanation']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}

class WordOrderSentenceSerializer(serializers.ModelSerializer):
     class Meta:
        model = WordOrderSentence
        fields = ['id', 'correct_order_words', 'distractor_words', 'display_prompt', 'explanation']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}

class PronunciationQuestionSerializer(serializers.ModelSerializer):
     class Meta:
        model = PronunciationQuestion
        fields = ['id', 'text_to_pronounce', 'explanation']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}

class SpellingQuestionSerializer(serializers.ModelSerializer):
     class Meta:
        model = SpellingQuestion
        fields = ['id', 'reference_spelling', 'explanation']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}


class TestSerializer(serializers.ModelSerializer):
    """Сериализатор для Теста с обработкой вложенных компонентов."""
    # Вложенные компоненты теперь указываем через их сериализаторы
    mcq_options = MCQOptionSerializer(many=True, required=False)
    free_text_question = FreeTextQuestionSerializer(required=False, allow_null=True)
    word_order_sentence = WordOrderSentenceSerializer(required=False, allow_null=True)
    matching_pairs = MatchingPairSerializer(many=True, required=False)
    matching_distractors = MatchingDistractorSerializer(many=True, required=False)
    pronunciation_question = PronunciationQuestionSerializer(required=False, allow_null=True)
    spelling_question = SpellingQuestionSerializer(required=False, allow_null=True)

    attached_image_details = ImageMaterialSerializer(source='attached_image', read_only=True)
    attached_audio_details = AudioMaterialSerializer(source='attached_audio', read_only=True)

    class Meta:
        model = Test
        fields = [
            'id', 'title', 'description', 'test_type',
            'attached_image', 'attached_audio',
            'attached_image_details', 'attached_audio_details',
            'created_by', 'created_at', 'updated_at',
            # Вложенные компоненты
            'mcq_options', 'free_text_question', 'word_order_sentence',
            'matching_pairs', 'matching_distractors',
            'pronunciation_question', 'spelling_question',
        ]
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'attached_image_details', 'attached_audio_details')

    def _handle_nested_create_update(self, test_instance, nested_data, model_class, related_name, serializer_class, many=False):
        """Вспомогательная функция для обработки вложенных данных."""
        if nested_data is None: # Если данные не переданы, ничего не делаем
             return

        if many:
            # Обработка ManyToMany или обратных ForeignKey
            existing_items = {item.id: item for item in getattr(test_instance, related_name).all()}
            items_to_create = []
            items_to_update = {}
            incoming_ids = set()

            for item_data in nested_data:
                item_id = item_data.get('id')
                if item_id:
                    incoming_ids.add(item_id)
                    if item_id in existing_items:
                         items_to_update[item_id] = item_data
                    else:
                         # Попытка обновить несуществующий элемент - можно вызвать ошибку или проигнорировать
                         pass
                else:
                    # Нет ID - значит, создаем новый
                    items_to_create.append(item_data)

            # Удаляем те, что не пришли в запросе
            ids_to_delete = set(existing_items.keys()) - incoming_ids
            if ids_to_delete:
                model_class.objects.filter(test=test_instance, id__in=ids_to_delete).delete()

            # Обновляем существующие
            for item_id, data in items_to_update.items():
                 item_instance = existing_items[item_id]
                 item_serializer = serializer_class(instance=item_instance, data=data, partial=True)
                 if item_serializer.is_valid(raise_exception=True):
                     item_serializer.save() # test уже установлен

            # Создаем новые
            for data in items_to_create:
                 # Убедимся, что 'id' не передается при создании
                 data.pop('id', None)
                 item_serializer = serializer_class(data=data)
                 if item_serializer.is_valid(raise_exception=True):
                     item_serializer.save(test=test_instance)
        else:
             # Обработка OneToOne
             existing_item = getattr(test_instance, related_name, None)
             if existing_item:
                  item_serializer = serializer_class(instance=existing_item, data=nested_data, partial=True)
                  if item_serializer.is_valid(raise_exception=True):
                      item_serializer.save() # test уже установлен
             elif nested_data: # Создаем, если данных нет, но пришли
                 item_serializer = serializer_class(data=nested_data)
                 if item_serializer.is_valid(raise_exception=True):
                      item_serializer.save(test=test_instance)


    @transaction.atomic
    def create(self, validated_data):
        # Извлекаем вложенные данные
        mcq_options_data = validated_data.pop('mcq_options', None)
        free_text_data = validated_data.pop('free_text_question', None)
        word_order_data = validated_data.pop('word_order_sentence', None)
        matching_pairs_data = validated_data.pop('matching_pairs', None)
        matching_distractors_data = validated_data.pop('matching_distractors', None)
        pronunciation_data = validated_data.pop('pronunciation_question', None)
        spelling_data = validated_data.pop('spelling_question', None)

        # Создаем основной объект теста
        test = Test.objects.create(**validated_data)

        # Создаем вложенные объекты
        self._handle_nested_create_update(test, mcq_options_data, MCQOption, 'mcq_options', MCQOptionSerializer, many=True)
        self._handle_nested_create_update(test, free_text_data, FreeTextQuestion, 'free_text_question', FreeTextQuestionSerializer, many=False)
        self._handle_nested_create_update(test, word_order_data, WordOrderSentence, 'word_order_sentence', WordOrderSentenceSerializer, many=False)
        self._handle_nested_create_update(test, matching_pairs_data, MatchingPair, 'matching_pairs', MatchingPairSerializer, many=True)
        self._handle_nested_create_update(test, matching_distractors_data, MatchingDistractor, 'matching_distractors', MatchingDistractorSerializer, many=True)
        self._handle_nested_create_update(test, pronunciation_data, PronunciationQuestion, 'pronunciation_question', PronunciationQuestionSerializer, many=False)
        self._handle_nested_create_update(test, spelling_data, SpellingQuestion, 'spelling_question', SpellingQuestionSerializer, many=False)

        return test

    @transaction.atomic
    def update(self, instance, validated_data):
         # Извлекаем вложенные данные
        mcq_options_data = validated_data.pop('mcq_options', None)
        free_text_data = validated_data.pop('free_text_question', None)
        word_order_data = validated_data.pop('word_order_sentence', None)
        matching_pairs_data = validated_data.pop('matching_pairs', None)
        matching_distractors_data = validated_data.pop('matching_distractors', None)
        pronunciation_data = validated_data.pop('pronunciation_question', None)
        spelling_data = validated_data.pop('spelling_question', None)

        # Обновляем основной объект теста
        instance = super().update(instance, validated_data)

        # Обновляем/создаем/удаляем вложенные объекты
        self._handle_nested_create_update(instance, mcq_options_data, MCQOption, 'mcq_options', MCQOptionSerializer, many=True)
        self._handle_nested_create_update(instance, free_text_data, FreeTextQuestion, 'free_text_question', FreeTextQuestionSerializer, many=False)
        self._handle_nested_create_update(instance, word_order_data, WordOrderSentence, 'word_order_sentence', WordOrderSentenceSerializer, many=False)
        self._handle_nested_create_update(instance, matching_pairs_data, MatchingPair, 'matching_pairs', MatchingPairSerializer, many=True)
        self._handle_nested_create_update(instance, matching_distractors_data, MatchingDistractor, 'matching_distractors', MatchingDistractorSerializer, many=True)
        self._handle_nested_create_update(instance, pronunciation_data, PronunciationQuestion, 'pronunciation_question', PronunciationQuestionSerializer, many=False)
        self._handle_nested_create_update(instance, spelling_data, SpellingQuestion, 'spelling_question', SpellingQuestionSerializer, many=False)

        instance.refresh_from_db() # Обновляем инстанс из БД
        return instance



# --- Сериализаторы для отправки ответов ---

class BaseSubmissionAnswerSerializer(serializers.Serializer):
    """Базовый класс для валидации ответов (можно использовать для разных типов)."""
    pass

class MCQSubmissionAnswerSerializer(BaseSubmissionAnswerSerializer):
    selected_option_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        min_length=1,
        help_text="Список ID выбранных вариантов ответа (MCQOption)."
    )

class FreeTextSubmissionAnswerSerializer(BaseSubmissionAnswerSerializer):
    answer_text = serializers.CharField(required=True, allow_blank=False)

class WordOrderSubmissionAnswerSerializer(BaseSubmissionAnswerSerializer):
    submitted_order_words = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        min_length=1,
        help_text="Список слов в порядке, указанном пользователем."
    )

class MatchingSubmissionAnswerItemSerializer(serializers.Serializer):
    """Ответ для одной пары в тесте на соотнесение."""
    matching_pair_id = serializers.IntegerField(required=True)
    submitted_answer_text = serializers.CharField(required=True, max_length=500)

class MatchingSubmissionAnswerSerializer(BaseSubmissionAnswerSerializer):
    answers = serializers.ListField(
        child=MatchingSubmissionAnswerItemSerializer(),
        required=True,
        min_length=1,
        help_text="Список соотнесений (пар) от пользователя."
    )

class PronunciationSubmissionAnswerSerializer(BaseSubmissionAnswerSerializer):
    pass

class SpellingSubmissionAnswerSerializer(BaseSubmissionAnswerSerializer):
    pass


class TestSubmissionInputSerializer(serializers.Serializer):
    """
    Сериализатор для входных данных при отправке теста (/api/tests/{test_pk}/submit/).
    Использует поле 'answers', которое должно соответствовать типу теста.
    """
    section_item_id = serializers.IntegerField(required=True, write_only=True)
    answers = serializers.JSONField(required=True, help_text="Объект с ответами, структура зависит от типа теста.")
    submitted_audio_file = serializers.FileField(required=False, allow_empty_file=False, write_only=True)
    submitted_image_file = serializers.ImageField(required=False, allow_empty_file=False, write_only=True)

    def validate_answers(self, answers_data):
        test = self.context.get('test')
        if not test:
            raise serializers.ValidationError("Не удалось определить тест для валидации ответов.")

        test_type = test.test_type
        answer_serializer = None

        if test_type in ['mcq-single', 'mcq-multi']:
            answer_serializer = MCQSubmissionAnswerSerializer(data=answers_data)
            if answer_serializer.is_valid():
                valid_option_ids = set(test.mcq_options.values_list('id', flat=True))
                submitted_ids = set(answers_data.get('selected_option_ids', []))
                if not submitted_ids.issubset(valid_option_ids):
                    raise serializers.ValidationError({"selected_option_ids": "Один или несколько ID вариантов ответа не принадлежат этому тесту."})
                if test_type == 'mcq-single' and len(submitted_ids) != 1:
                    raise serializers.ValidationError({"selected_option_ids": "Для этого теста должен быть выбран ровно один вариант."})
        elif test_type == 'free-text':
            answer_serializer = FreeTextSubmissionAnswerSerializer(data=answers_data)
        elif test_type == 'word-order':
             # Фронтенд гарантирует правильность, только валидация структуры
            answer_serializer = WordOrderSubmissionAnswerSerializer(data=answers_data)
        elif test_type == 'matching':
             # Фронтенд гарантирует правильность, только валидация структуры
            answer_serializer = MatchingSubmissionAnswerSerializer(data=answers_data)
            if answer_serializer.is_valid(): # Проверяем внутреннюю структуру
                 valid_pair_ids = set(test.matching_pairs.values_list('id', flat=True))
                 submitted_pair_ids = set(item['matching_pair_id'] for item in answers_data.get('answers', []))
                 if not submitted_pair_ids.issubset(valid_pair_ids):
                      raise serializers.ValidationError({"answers": "Один или несколько ID пар для соотнесения не принадлежат этому тесту."})
        elif test_type in ['pronunciation', 'spelling']:
             # Валидации JSON нет, только проверка файла в validate()
            pass
        else:
            raise serializers.ValidationError(f"Неизвестный тип теста для валидации ответов: {test_type}")

        if answer_serializer and not answer_serializer.is_valid():
            raise serializers.ValidationError({"answers": answer_serializer.errors})

        return answers_data

    def validate(self, attrs):
        test = self.context.get('test')
        if test:
            if test.test_type == 'pronunciation' and 'submitted_audio_file' not in self.context['request'].FILES:
                 raise serializers.ValidationError({"submitted_audio_file": "Для теста на произношение необходим аудио файл."})
            if test.test_type == 'spelling' and 'submitted_image_file' not in self.context['request'].FILES:
                 raise serializers.ValidationError({"submitted_image_file": "Для теста на правописание необходимо изображение."})
        return attrs


class MCQSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
    selected_options = MCQOptionSerializer(many=True, read_only=True)
    class Meta:
        model = MCQSubmissionAnswer
        fields = ['id', 'selected_options']

class FreeTextSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
     class Meta:
        model = FreeTextSubmissionAnswer
        fields = ['id', 'answer_text']

class WordOrderSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
     class Meta:
        model = WordOrderSubmissionAnswer
        fields = ['id', 'submitted_order_words']

class PronunciationSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
    submitted_audio_url = serializers.SerializerMethodField()
    class Meta:
        model = PronunciationSubmissionAnswer
        fields = ['id', 'submitted_audio_url']

    def get_submitted_audio_url(self, obj):
        request = self.context.get('request')
        if request and obj.submitted_audio_file:
            return request.build_absolute_uri(obj.submitted_audio_file.url)
        return None

class SpellingSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
    submitted_image_url = serializers.SerializerMethodField()
    class Meta:
        model = SpellingSubmissionAnswer
        fields = ['id', 'submitted_image_url']

    def get_submitted_image_url(self, obj):
        request = self.context.get('request')
        if request and obj.submitted_image_file:
            return request.build_absolute_uri(obj.submitted_image_file.url)
        return None
    

class MatchingSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
     matching_pair_prompt_text = serializers.CharField(source='matching_pair.prompt_text', read_only=True, allow_null=True)
     class Meta:
        model = MatchingSubmissionAnswer
        fields = ['id', 'matching_pair_id', 'matching_pair_prompt_text', 'submitted_answer_text']


class TestSubmissionDetailSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    test = TestSerializer(read_only=True)
    answers = serializers.SerializerMethodField()
    # section_item_details = ?

    class Meta:
        model = TestSubmission
        fields = [
            'id', 'test', 'student', 'section_item', 'submitted_at',
            'status', 'score', 'feedback', 'answers'
        ]

    def get_answers(self, obj):
        test_type = obj.test.test_type
        context = self.context

        try:
            if test_type in ['mcq-single', 'mcq-multi'] and hasattr(obj, 'mcq_answers'):
                mcq_answer_instance = obj.mcq_answers.first()
                if mcq_answer_instance:
                    selected_options = mcq_answer_instance.selected_options.all()
                    return MCQOptionSerializer(selected_options, many=True, context=context).data
                return []
            elif test_type == 'free-text' and hasattr(obj, 'free_text_answer'):
                return FreeTextSubmissionAnswerDetailSerializer(obj.free_text_answer, context=context).data
            elif test_type == 'word-order' and hasattr(obj, 'word_order_answer'):
                return WordOrderSubmissionAnswerDetailSerializer(obj.word_order_answer, context=context).data
            elif test_type == 'matching' and hasattr(obj, 'matching_answers'):
                return MatchingSubmissionAnswerDetailSerializer(obj.matching_answers.all(), many=True, context=context).data
            elif test_type == 'pronunciation' and hasattr(obj, 'pronunciation_answer'):
                return PronunciationSubmissionAnswerDetailSerializer(obj.pronunciation_answer, context=context).data
            elif test_type == 'spelling' and hasattr(obj, 'spelling_answer'):
                return SpellingSubmissionAnswerDetailSerializer(obj.spelling_answer, context=context).data
        except Exception as e:
             print(f"Error serializing answers for submission {obj.id}: {e}")
             return None
        return None
    
class TestSubmissionListSerializer(serializers.ModelSerializer):
    """Краткая информация об отправке для списков."""
    student = UserSerializer(read_only=True)
    test_title = serializers.CharField(source='test.title', read_only=True)

    class Meta:
        model = TestSubmission
        fields = ['id', 'test', 'test_title', 'student', 'submitted_at', 'status', 'score']
