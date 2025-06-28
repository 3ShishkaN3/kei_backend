from rest_framework import serializers
from rest_framework import serializers
from .models import (
    TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial,
    Test, MCQOption, FreeTextQuestion, WordOrderSentence, MatchingPair, DragDropSubmissionAnswer,
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
    id = serializers.IntegerField(required=False, allow_null=True)
    prompt_image_details = ImageMaterialSerializer(source='prompt_image', read_only=True, allow_null=True)
    prompt_audio_details = AudioMaterialSerializer(source='prompt_audio', read_only=True, allow_null=True)
    
    class Meta:
        model = MatchingPair
        fields = [
            'id', 'prompt_text',
            'prompt_image', 'prompt_audio', # Actual FK fields for input/output
            'prompt_image_details', 'prompt_audio_details', # Read-only for output
            'correct_answer_text', 'order', 'explanation'
        ]
        extra_kwargs = {
            'test': {'read_only': True, 'required': False}, # Связь с Test устанавливается в TestSerializer
            'order': {'required': False}, # Порядок будет управляться при сохранении
            'correct_answer_text': {'required': True, 'allow_blank': False}, # Обязательное поле
            'prompt_image': {'required': False, 'allow_null': True}, # Allow null for FK
            'prompt_audio': {'required': False, 'allow_null': True}, # Allow null for FK
        }

    def _get_request_user(self):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return request.user
        return None

    def _create_material_from_file(self, file_data, material_model_class, user, title_prefix="Prompt Attachment"):
        if not file_data:
            return None
        file_field_name_in_material = material_model_class.get_file_field_name()

        return material_model_class.objects.create(
            **{file_field_name_in_material: file_data},
            created_by=user
        )

    def _delete_material_if_exists(self, material_instance):
        if material_instance:
            file_field_name = getattr(material_instance, 'get_file_field_name', lambda: 'file')()
            file_field = getattr(material_instance, file_field_name, None)
            if file_field: file_field.delete(save=False)
            material_instance.delete()

    def create(self, validated_data):
        # prompt_image_file and prompt_audio_file are now handled by the parent serializer (TestSerializer)
        # and passed directly as arguments to this create method.
        prompt_image_file = self.context.get('prompt_image_file')
        prompt_audio_file = self.context.get('prompt_audio_file')

        user = self._get_request_user()

        # Handle prompt_image_file
        if prompt_image_file:
            image_material = self._create_material_from_file(prompt_image_file, ImageMaterial, user, "MatchingPair Image")
            validated_data['prompt_image'] = image_material
        elif 'prompt_image' in validated_data and validated_data['prompt_image'] is None:
            validated_data['prompt_image'] = None # Ensure it's explicitly set to None if provided as such

        # Handle prompt_audio_file
        if prompt_audio_file:
            audio_material = self._create_material_from_file(prompt_audio_file, AudioMaterial, user, "MatchingPair Audio")
            validated_data['prompt_audio'] = audio_material
        elif 'prompt_audio' in validated_data and validated_data['prompt_audio'] is None:
            validated_data['prompt_audio'] = None # Ensure it's explicitly set to None if provided as such

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # prompt_image_file and prompt_audio_file are now handled by the parent serializer (TestSerializer)
        # and passed directly as arguments to this update method.
        prompt_image_file = self.context.get('prompt_image_file')
        prompt_audio_file = self.context.get('prompt_audio_file')

        user = self._get_request_user()

        # Handle prompt_image_file update
        if prompt_image_file:
            if instance.prompt_image:
                self._delete_material_if_exists(instance.prompt_image)
            new_image_material = self._create_material_from_file(prompt_image_file, ImageMaterial, user, "MatchingPair Image")
            validated_data['prompt_image'] = new_image_material
        elif 'prompt_image' in validated_data and validated_data['prompt_image'] is None:
            if instance.prompt_image:
                self._delete_material_if_exists(instance.prompt_image)
            validated_data['prompt_image'] = None

        # Handle prompt_audio_file update
        if prompt_audio_file:
            if instance.prompt_audio:
                self._delete_material_if_exists(instance.prompt_audio)
            new_audio_material = self._create_material_from_file(prompt_audio_file, AudioMaterial, user, "MatchingPair Audio")
            validated_data['prompt_audio'] = new_audio_material
        elif 'prompt_audio' in validated_data and validated_data['prompt_audio'] is None:
            if instance.prompt_audio:
                self._delete_material_if_exists(instance.prompt_audio)
            validated_data['prompt_audio'] = None

        return super().update(instance, validated_data)



# Добавляем сериализаторы для других компонентов (даже если они простые)
class FreeTextQuestionSerializer(serializers.ModelSerializer):
     class Meta:
        model = FreeTextQuestion
        fields = ['id', 'reference_answer', 'explanation']
        extra_kwargs = {'test': {'read_only': True, 'required': False}}

class WordOrderSentenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = WordOrderSentence
        fields = ['id', 'correct_ordered_texts', 'display_prompt', 'explanation'] 
        extra_kwargs = {
            'test': {'read_only': True, 'required': False},
            'correct_ordered_texts': {'required': True}
        }

    def validate_correct_ordered_texts(self, value):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("Поле 'correct_ordered_texts' должно быть списком строк.")
        if not value:
            raise serializers.ValidationError("Список 'correct_ordered_texts' не может быть пустым.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return attrs

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
    mcq_options = MCQOptionSerializer(many=True, required=False, allow_null=True)
    free_text_question = FreeTextQuestionSerializer(required=False, allow_null=True)
    word_order_sentence = WordOrderSentenceSerializer(required=False, allow_null=True) 
    drag_drop_slots = MatchingPairSerializer(many=True, required=False, allow_null=True) 
    pronunciation_question = PronunciationQuestionSerializer(required=False, allow_null=True)
    spelling_question = SpellingQuestionSerializer(required=False, allow_null=True)

    attached_image_details = ImageMaterialSerializer(source='attached_image', read_only=True, allow_null=True)
    attached_audio_details = AudioMaterialSerializer(source='attached_audio', read_only=True, allow_null=True)

    attached_image_file = serializers.ImageField(write_only=True, required=False, allow_null=True)
    attached_audio_file = serializers.FileField(write_only=True, required=False, allow_null=True)
    
    created_by_details = UserSerializer(source='created_by', read_only=True)

    class Meta:
        model = Test
        fields = [
            'id', 'title', 'description', 'test_type',
            'attached_image', 'attached_audio', 
            'attached_image_details', 'attached_audio_details',
            'created_by', 'created_by_details', 
            'created_at', 'updated_at',
            
            'mcq_options', 
            'free_text_question', 
            'word_order_sentence',
            'draggable_options_pool', # Новое поле для drag-and-drop
            'drag_drop_slots',      # Новое поле для drag-and-drop
            'pronunciation_question', 
            'spelling_question',
            'attached_image_file', 
            'attached_audio_file',
        ]
        read_only_fields = ('id', 'created_by', 'created_by_details', 
                            'created_at', 'updated_at', 
                            'attached_image_details', 'attached_audio_details')
        extra_kwargs = {
            'attached_image': {'required': False, 'allow_null': True},
            'attached_audio': {'required': False, 'allow_null': True},
            'draggable_options_pool': {'required': False, 'allow_null': True},
        }

    def _get_request_user(self):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return request.user
        return None

    def _create_material_from_file(self, file_data, material_model_class, user, title_prefix="Test Attachment"):
        if not file_data:
            return None
        file_field_name_in_material = material_model_class.get_file_field_name() 
        
        return material_model_class.objects.create(
            **{file_field_name_in_material: file_data}, # {'image': file_data} {'audio_file': file_data}
            created_by=user
        )

    def _delete_material_if_exists(self, material_instance):
        if material_instance:
            file_field_name = getattr(material_instance, 'get_file_field_name', lambda: 'file')()
            file_field = getattr(material_instance, file_field_name, None)
            if file_field: file_field.delete(save=False)
            material_instance.delete()

    def _handle_attached_file_on_create(self, validated_data_for_test, file_data, fk_field_name_on_test, material_model_class):
        user = self._get_request_user()
        if file_data:
            new_material = self._create_material_from_file(file_data, material_model_class, user, validated_data_for_test.get('title', 'Test'))
            validated_data_for_test[fk_field_name_on_test] = new_material 
        elif fk_field_name_on_test in validated_data_for_test and validated_data_for_test[fk_field_name_on_test] is None:
            validated_data_for_test[fk_field_name_on_test] = None

    def _handle_attached_file_on_update(self, test_instance, file_data, fk_field_name_on_test, material_model_class, requested_fk_id_action, marker_object):
        user = self._get_request_user()
        current_material_on_instance = getattr(test_instance, fk_field_name_on_test, None)
        if file_data: 
            if current_material_on_instance: self._delete_material_if_exists(current_material_on_instance)
            new_material = self._create_material_from_file(file_data, material_model_class, user, test_instance.title)
            setattr(test_instance, fk_field_name_on_test, new_material)
        elif requested_fk_id_action is None: 
            if current_material_on_instance:
                self._delete_material_if_exists(current_material_on_instance)
            setattr(test_instance, fk_field_name_on_test, None)
        elif requested_fk_id_action is not marker_object: 
            new_fk_id = None
            try: new_fk_id = int(requested_fk_id_action) if requested_fk_id_action is not None else None
            except (ValueError, TypeError): pass
            current_fk_id_val = getattr(test_instance, f"{fk_field_name_on_test}_id", None)
            if new_fk_id != current_fk_id_val:
                if new_fk_id is not None:
                    try:
                        material_to_link = material_model_class.objects.get(pk=new_fk_id)
                        if current_material_on_instance and current_material_on_instance.id != new_fk_id : # Удаляем старый, если он был и заменяется на другой существующий
                            self._delete_material_if_exists(current_material_on_instance)
                        setattr(test_instance, fk_field_name_on_test, material_to_link)
                    except material_model_class.DoesNotExist:
                        raise serializers.ValidationError({fk_field_name_on_test: f"Материал с ID {new_fk_id} не найден."})
                else: # new_fk_id is None, это уже обработано `requested_fk_id_action is None`
                    pass 

    def _handle_nested_many_to_many(self, test_instance, nested_data_list, related_manager_name, item_serializer_class, slot_image_files=None, slot_audio_files=None):
        if nested_data_list is None:
            return
        manager = getattr(test_instance, related_manager_name)
        existing_items_map = {item.id: item for item in manager.all()}
        current_ids_in_payload = set()
        order_counter = 0
        for item_data in nested_data_list:
            item_id = item_data.get('id')
            item_data['order'] = order_counter

            # Prepare context for nested serializer with specific file for this slot
            nested_serializer_context = self.context.copy()
            nested_serializer_context['prompt_image_file'] = slot_image_files[order_counter] if slot_image_files and order_counter < len(slot_image_files) else None
            nested_serializer_context['prompt_audio_file'] = slot_audio_files[order_counter] if slot_audio_files and order_counter < len(slot_audio_files) else None

            if item_id and item_id in existing_items_map:
                item_serializer = item_serializer_class(existing_items_map[item_id], data=item_data, partial=True, context=nested_serializer_context)
                item_serializer.is_valid(raise_exception=True)
                item_serializer.save()
                current_ids_in_payload.add(item_id)
            else:
                item_data.pop('id', None)
                item_serializer = item_serializer_class(data=item_data, context=nested_serializer_context)
                item_serializer.is_valid(raise_exception=True)
                new_item = item_serializer.save(test=test_instance)
                current_ids_in_payload.add(new_item.id)
            order_counter += 1 # Increment after processing each item
        ids_to_delete = set(existing_items_map.keys()) - current_ids_in_payload
        if ids_to_delete:
            manager.filter(id__in=ids_to_delete).delete()

    def _handle_nested_one_to_one(self, test_instance, nested_data, related_name_on_test, item_serializer_class):
        if nested_data is None and self.partial and related_name_on_test not in self.initial_data: return
        existing_item = getattr(test_instance, related_name_on_test, None)
        if nested_data: 
            if existing_item:
                item_serializer = item_serializer_class(instance=existing_item, data=nested_data, partial=True, context=self.context)
                item_serializer.is_valid(raise_exception=True); item_serializer.save()
            else:
                item_serializer = item_serializer_class(data=nested_data, context=self.context)
                item_serializer.is_valid(raise_exception=True); item_serializer.save(test=test_instance)
        elif existing_item: 
             existing_item.delete()
             # setattr(test_instance, related_name_on_test, None) # Не нужно, ForeignKey обнулится при save instance

    def validate(self, attrs):
        attrs = super().validate(attrs) 
        test_type = attrs.get('test_type', getattr(self.instance, 'test_type', None))
        

        options_pool_data = attrs.get('draggable_options_pool')
        if options_pool_data is None:
            if self.instance: 
                options_pool_data = self.instance.draggable_options_pool
            else: # Создание
                options_pool_data = [] 
                attrs['draggable_options_pool'] = options_pool_data # Добавляем, если не было

        if not isinstance(options_pool_data, list) or not all(isinstance(opt, str) for opt in options_pool_data):
            raise serializers.ValidationError({"draggable_options_pool": "Должен быть списком строк."})
        options_pool_set = set(options_pool_data)

        if test_type == 'drag-and-drop':
            slots_data = attrs.get('drag_drop_slots')
            if slots_data: 
                for slot_idx, slot_data in enumerate(slots_data):
                    correct_answer = slot_data.get('correct_answer_text')
                    if not correct_answer:
                        raise serializers.ValidationError({
                            "drag_drop_slots": f"Для слота #{slot_idx+1} должен быть указан 'correct_answer_text'."
                        })
                    if correct_answer not in options_pool_set:
                        raise serializers.ValidationError({
                            "drag_drop_slots": f"Значение '{correct_answer}' (слот #{slot_idx+1}) отсутствует в 'draggable_options_pool'."
                        })
        
        elif test_type == 'word-order':
            word_order_data = attrs.get('word_order_sentence_details') 
            if not word_order_data and self.instance and self.instance.word_order_sentence_details: 
                word_order_data = WordOrderSentenceSerializer(self.instance.word_order_sentence_details).data 
            
            if word_order_data: 
                correct_texts = word_order_data.get('correct_ordered_texts')
                if not correct_texts or not isinstance(correct_texts, list):
                    raise serializers.ValidationError({
                        "word_order_sentence": "Поле 'correct_ordered_texts' обязательно и должно быть списком строк."
                    })
                for text_item in correct_texts:
                    if not isinstance(text_item, str):
                        raise serializers.ValidationError({
                             "word_order_sentence": "Каждый элемент в 'correct_ordered_texts' должен быть строкой."
                        })
                    if text_item not in options_pool_set:
                        raise serializers.ValidationError({
                            "word_order_sentence": f"Текст '{text_item}' из 'correct_ordered_texts' отсутствует в 'draggable_options_pool' теста."
                        })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        mcq_options_data = validated_data.pop('mcq_options', [])
        drag_drop_slots_data = validated_data.pop('drag_drop_slots', [])
        free_text_data = validated_data.pop('free_text_question', None)
        word_order_data = validated_data.pop('word_order_sentence', None)
        pronunciation_data = validated_data.pop('pronunciation_question', None)
        spelling_data = validated_data.pop('spelling_question', None)

        image_file = validated_data.pop('attached_image_file', None)
        audio_file = validated_data.pop('attached_audio_file', None)
        
        self._handle_attached_file_on_create(validated_data, image_file, 'attached_image', ImageMaterial)
        self._handle_attached_file_on_create(validated_data, audio_file, 'attached_audio', AudioMaterial)
        
        user = self._get_request_user()
        if 'created_by' not in validated_data and user:
            validated_data['created_by'] = user
        
        test_instance = Test.objects.create(**validated_data)

        # Get the list of files from the request context
        request_files = self.context.get('request').FILES if 'request' in self.context else {}
        slot_image_files = request_files.getlist('prompt_image_file')
        slot_audio_files = request_files.getlist('prompt_audio_file')

        self._handle_nested_many_to_many(test_instance, mcq_options_data, 'mcq_options', MCQOptionSerializer)
        self._handle_nested_many_to_many(test_instance, drag_drop_slots_data, 'drag_drop_slots', MatchingPairSerializer, slot_image_files=slot_image_files, slot_audio_files=slot_audio_files)
        self._handle_nested_one_to_one(test_instance, free_text_data, 'free_text_question', FreeTextQuestionSerializer)
        self._handle_nested_one_to_one(test_instance, word_order_data, 'word_order_sentence', WordOrderSentenceSerializer)
        self._handle_nested_one_to_one(test_instance, pronunciation_data, 'pronunciation_question', PronunciationQuestionSerializer)
        self._handle_nested_one_to_one(test_instance, spelling_data, 'spelling_question', SpellingQuestionSerializer)

        return test_instance

    @transaction.atomic
    def update(self, instance, validated_data):
        mcq_options_data = validated_data.pop('mcq_options', None) 
        drag_drop_slots_data = validated_data.pop('drag_drop_slots', None)
        free_text_data = validated_data.pop('free_text_question', None)
        word_order_data = validated_data.pop('word_order_sentence', None)
        pronunciation_data = validated_data.pop('pronunciation_question', None)
        spelling_data = validated_data.pop('spelling_question', None)

        image_file_from_request = validated_data.pop('attached_image_file', None)
        audio_file_from_request = validated_data.pop('attached_audio_file', None)
        
        marker = object() 
        requested_image_id_action = validated_data.pop('attached_image', marker) 
        requested_audio_id_action = validated_data.pop('attached_audio', marker)

        self._handle_attached_file_on_update(instance, image_file_from_request, 'attached_image', ImageMaterial, requested_image_id_action, marker)
        self._handle_attached_file_on_update(instance, audio_file_from_request, 'attached_audio', AudioMaterial, requested_audio_id_action, marker)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Get the list of files from the request context
        request_files = self.context.get('request').FILES if 'request' in self.context else {}
        slot_image_files = request_files.getlist('prompt_image_file')
        slot_audio_files = request_files.getlist('prompt_audio_file')

        if mcq_options_data is not None:
            self._handle_nested_many_to_many(instance, mcq_options_data, 'mcq_options', MCQOptionSerializer)
        if drag_drop_slots_data is not None:
            self._handle_nested_many_to_many(instance, drag_drop_slots_data, 'drag_drop_slots', MatchingPairSerializer, slot_image_files=slot_image_files, slot_audio_files=slot_audio_files)
        
        if free_text_data is not None or ('free_text_question' in self.initial_data and self.initial_data.get('free_text_question') is None):
             self._handle_nested_one_to_one(instance, free_text_data, 'free_text_question', FreeTextQuestionSerializer)
        if word_order_data is not None or ('word_order_sentence' in self.initial_data and self.initial_data.get('word_order_sentence') is None):
            self._handle_nested_one_to_one(instance, word_order_data, 'word_order_sentence', WordOrderSentenceSerializer)
        if pronunciation_data is not None or ('pronunciation_question' in self.initial_data and self.initial_data.get('pronunciation_question') is None):
            self._handle_nested_one_to_one(instance, pronunciation_data, 'pronunciation_question', PronunciationQuestionSerializer)
        if spelling_data is not None or ('spelling_question' in self.initial_data and self.initial_data.get('spelling_question') is None):
            self._handle_nested_one_to_one(instance, spelling_data, 'spelling_question', SpellingQuestionSerializer)
        
        instance.refresh_from_db()
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

class DragDropSubmissionAnswerItemSerializer(serializers.Serializer):
    slot_id = serializers.IntegerField(required=True)
    dropped_option_text = serializers.CharField(max_length=500, required=True, allow_blank=False)

class DragDropSubmissionAnswerInputSerializer(BaseSubmissionAnswerSerializer):
    answers = serializers.ListField(
        child=DragDropSubmissionAnswerItemSerializer(), required=True, min_length=0, allow_empty=True
    )

class DragDropSubmissionAnswerDetailSerializer(serializers.ModelSerializer):
    slot_id = serializers.IntegerField(source='slot.id')
    slot_prompt_text = serializers.CharField(source='slot.prompt_text', read_only=True, allow_null=True)
    slot_correct_answer_text = serializers.CharField(source='slot.correct_answer_text', read_only=True)
    
    # Для отображения деталей prompt_image/audio из связанного слота (MatchingPair)
    prompt_image_details = ImageMaterialSerializer(source='slot.prompt_image', read_only=True, allow_null=True)
    prompt_audio_details = AudioMaterialSerializer(source='slot.prompt_audio', read_only=True, allow_null=True)

    class Meta:
        model = DragDropSubmissionAnswer
        fields = [
            'id', 'slot_id', 'slot_prompt_text', 
            'prompt_image_details', 'prompt_audio_details',
            'dropped_option_text', 'is_correct', 'slot_correct_answer_text'
        ]

class MCQSubmissionAnswerOutputSerializer(serializers.ModelSerializer):
    selected_options = MCQOptionSerializer(many=True, read_only=True)

    class Meta:
        model = MCQSubmissionAnswer
        fields = ['selected_options']

class FreeTextSubmissionAnswerOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = FreeTextSubmissionAnswer
        fields = ['answer_text']

class WordOrderSubmissionAnswerOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = WordOrderSubmissionAnswer
        fields = ['submitted_order_words']

class PronunciationSubmissionAnswerOutputSerializer(serializers.ModelSerializer):
    # Assuming submitted_audio_file URL is needed
    submitted_audio_file = serializers.FileField(read_only=True) 
    class Meta:
        model = PronunciationSubmissionAnswer
        fields = ['submitted_audio_file']

class SpellingSubmissionAnswerOutputSerializer(serializers.ModelSerializer):
    # Assuming submitted_image_file URL is needed
    submitted_image_file = serializers.ImageField(read_only=True)
    class Meta:
        model = SpellingSubmissionAnswer
        fields = ['submitted_image_file']

class TestSubmissionDetailSerializer(serializers.ModelSerializer):
    test_details = TestSerializer(source='test', read_only=True)
    student_details = UserSerializer(source='student', read_only=True)
    # section_item_details = SectionItemSerializer(source='section_item', read_only=True) # Removed due to circular import

    # Nested serializers for answers based on test type
    mcq_answers = MCQSubmissionAnswerOutputSerializer(read_only=True)
    free_text_answer = FreeTextSubmissionAnswerOutputSerializer(read_only=True)
    word_order_answer = WordOrderSubmissionAnswerOutputSerializer(read_only=True)
    drag_drop_answers = DragDropSubmissionAnswerDetailSerializer(many=True, read_only=True)
    pronunciation_answer = PronunciationSubmissionAnswerOutputSerializer(read_only=True)
    spelling_answer = SpellingSubmissionAnswerOutputSerializer(read_only=True)

    class Meta:
        model = TestSubmission
        fields = [
            'id', 'test', 'test_details', 'student', 'student_details',
            'section_item', 'submitted_at', 'status', 'score', 'feedback',
            'mcq_answers', 'free_text_answer', 'word_order_answer',
            'drag_drop_answers', 'pronunciation_answer', 'spelling_answer'
        ]
        read_only_fields = (
            'id', 'test', 'test_details', 'student', 'student_details',
            'section_item', 'submitted_at', 'status', 'score', 'feedback',
            'mcq_answers', 'free_text_answer', 'word_order_answer',
            'drag_drop_answers', 'pronunciation_answer', 'spelling_answer'
        )

class TestSubmissionListSerializer(serializers.ModelSerializer):
    test_title = serializers.CharField(source='test.title', read_only=True)
    student_username = serializers.CharField(source='student.username', read_only=True)
    test_type = serializers.CharField(source='test.test_type', read_only=True)

    class Meta:
        model = TestSubmission
        fields = [
            'id', 'test', 'test_title', 'student', 'student_username',
            'submitted_at', 'status', 'score', 'test_type'
        ]
        read_only_fields = (
            'id', 'test', 'test_title', 'student', 'student_username',
            'submitted_at', 'status', 'score', 'test_type'
        )


class TestSubmissionInputSerializer(serializers.Serializer):
    section_item_id = serializers.IntegerField(required=True, write_only=True)
    answers = serializers.JSONField(required=True)
    submitted_audio_file = serializers.FileField(required=False, allow_empty_file=True, write_only=True, allow_null=True)
    submitted_image_file = serializers.ImageField(required=False, allow_empty_file=True, write_only=True, allow_null=True)

    def validate_answers(self, answers_data_from_json_field):
        test = self.context.get('test')
        if not test: raise serializers.ValidationError("Тест не определен для валидации ответов.")
        test_type = test.test_type
        
        answer_validator_serializer = None
        validation_errors = {}

        if test_type in ['mcq-single', 'mcq-multi']:
            answer_validator_serializer = MCQSubmissionAnswerSerializer(data=answers_data_from_json_field)
            if answer_validator_serializer.is_valid():
                valid_option_ids = set(test.mcq_options.values_list('id', flat=True))
                submitted_ids = set(answer_validator_serializer.validated_data.get('selected_option_ids', []))
                if not submitted_ids.issubset(valid_option_ids) and submitted_ids: # Проверяем только если есть отправленные ID
                    validation_errors['selected_option_ids'] = "Один или несколько ID вариантов ответа не принадлежат этому тесту."
                if test_type == 'mcq-single' and len(submitted_ids) > 1 : # Пустой массив для single означает нет ответа
                    validation_errors['selected_option_ids'] = "Для этого теста должен быть выбран не более одного варианта."
            else:
                validation_errors = answer_validator_serializer.errors
        
        elif test_type == 'free-text':
            answer_validator_serializer = FreeTextSubmissionAnswerSerializer(data=answers_data_from_json_field)
            if not answer_validator_serializer.is_valid(): validation_errors = answer_validator_serializer.errors
        
        elif test_type == 'word-order':
            answer_validator_serializer = WordOrderSubmissionAnswerSerializer(data=answers_data_from_json_field)
            if not answer_validator_serializer.is_valid(): validation_errors = answer_validator_serializer.errors
        
        elif test_type == 'drag-and-drop':
            answer_validator_serializer = DragDropSubmissionAnswerInputSerializer(data=answers_data_from_json_field)
            if answer_validator_serializer.is_valid():
                valid_slot_ids = set(test.drag_drop_slots.values_list('id', flat=True))
                options_pool = set(test.draggable_options_pool)
                for ans_item in answer_validator_serializer.validated_data.get('answers', []):
                    if ans_item['slot_id'] not in valid_slot_ids:
                        validation_errors.setdefault('answers', []).append(f"Слот ID {ans_item['slot_id']} недействителен.")
                    if ans_item['dropped_option_text'] not in options_pool:
                         validation_errors.setdefault('answers', []).append(f"Текст облачка '{ans_item['dropped_option_text']}' не из пула.")
            else:
                 validation_errors = answer_validator_serializer.errors
        
        elif test_type in ['pronunciation', 'spelling']:
            pass # Валидация файла происходит в общем validate методе
        
        else:
            raise serializers.ValidationError(f"Неизвестный тип теста для валидации ответов: {test_type}")

        if validation_errors:
            raise serializers.ValidationError({"answers": validation_errors})

        return answers_data_from_json_field 

    def validate(self, attrs):
        test = self.context.get('test')
        # Файлы уже будут в self.initial_data.get('submitted_audio_file') и т.д. если это multipart
        # или в attrs['submitted_audio_file'] если они были в JSON (не наш случай для файлов)
        # request.FILES доступен через self.context['request'].FILES
        request_files = self.context['request'].FILES if 'request' in self.context else {}

        if test:
            if test.test_type == 'pronunciation' and 'submitted_audio_file' not in request_files:
                 raise serializers.ValidationError({"submitted_audio_file": "Для теста на произношение необходим аудио файл."})
            if test.test_type == 'spelling' and 'submitted_image_file' not in request_files:
                 raise serializers.ValidationError({"submitted_image_file": "Для теста на правописание необходимо изображение."})
        return attrs
