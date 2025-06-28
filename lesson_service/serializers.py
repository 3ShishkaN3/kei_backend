import json
from rest_framework import serializers
from .models import Lesson, Section, SectionCompletion, LessonCompletion, SectionItem
from auth_service.serializers import UserSerializer
from material_service.serializers import (
    TextMaterialSerializer, ImageMaterialSerializer, AudioMaterialSerializer,
    VideoMaterialSerializer, DocumentMaterialSerializer, TestSerializer
)
from material_service.models import (
    TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial, Test
)

CONTENT_TYPE_MAP = {
    'text': {'model': TextMaterial, 'serializer': TextMaterialSerializer},
    'image': {'model': ImageMaterial, 'serializer': ImageMaterialSerializer},
    'audio': {'model': AudioMaterial, 'serializer': AudioMaterialSerializer},
    'video': {'model': VideoMaterial, 'serializer': VideoMaterialSerializer},
    'document': {'model': DocumentMaterial, 'serializer': DocumentMaterialSerializer},
    'test': {'model': Test, 'serializer': TestSerializer},
}

class SectionItemSerializer(serializers.ModelSerializer):
    content_details = serializers.SerializerMethodField(read_only=True)
    content_data = serializers.JSONField(write_only=True, required=False, allow_null=True,
                                         help_text="JSON-объект с данными для создания нового контента (текста, теста и т.д.) или метаданные для файлов.")
    existing_content_type = serializers.CharField(write_only=True, required=False, allow_null=True, help_text="Тип существующего контента (напр., 'text', 'test')")
    existing_content_id = serializers.IntegerField(write_only=True, required=False, allow_null=True, help_text="ID существующего контента")

    class Meta:
        model = SectionItem
        fields = [
            'id', 'section', 'order', 'item_type',
            'content_details',
            'content_data', 'existing_content_type', 'existing_content_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ('section', 'created_at', 'updated_at')
        extra_kwargs = {
            'item_type': {'required': True, 'allow_blank': False},
            'order': {'required': False}, # Order будет вычисляться во ViewSet для создания
        }

    def get_content_details(self, obj):
        content_object = obj.content_object
        if content_object:
            item_type = obj.item_type
            if item_type in CONTENT_TYPE_MAP:
                serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                context = self.context
                if 'request' not in context and hasattr(self, 'root') and hasattr(self.root, 'context'): # Попытка получить request из root
                    context['request'] = self.root.context.get('request')
                elif 'request' not in context:
                     context['request'] = None

                try:
                    return serializer_class(content_object, context=context).data
                except Exception as e:
                    # В реальном проекте здесь лучше использовать logging
                    print(f"Error serializing content for item {obj.id} (type: {item_type}): {e}")
                    return {"error": "Could not serialize content details."}
        return None

    def validate(self, attrs):
        raw_initial_data = self.initial_data
        # item_type берется из attrs, так как он 'required': True и должен быть там после базовой валидации
        item_type = attrs['item_type']

        is_update = self.instance is not None
        
        content_creation_data_from_json_field = None
        files_for_material = {}

        content_data_json_str = raw_initial_data.get('content_data')
        if content_data_json_str:
            if isinstance(content_data_json_str, str):
                try:
                    content_creation_data_from_json_field = json.loads(content_data_json_str)
                except json.JSONDecodeError:
                    raise serializers.ValidationError({'content_data': 'Некорректный JSON в поле content_data.'})
            elif isinstance(content_data_json_str, dict):
                 content_creation_data_from_json_field = content_data_json_str
            else:
                raise serializers.ValidationError({'content_data': 'Поле content_data должно быть JSON-строкой или объектом.'})
        
        request_files = self.context['request'].FILES if 'request' in self.context and hasattr(self.context['request'], 'FILES') else {}
        for field_name, uploaded_file in request_files.items():
            files_for_material[field_name] = uploaded_file
            
        final_material_data_payload = {}
        if content_creation_data_from_json_field:
            final_material_data_payload.update(content_creation_data_from_json_field)
        final_material_data_payload.update(files_for_material) # Файлы перезапишут одноименные ключи из JSON, если есть

        # existing_content_type и existing_content_id уже будут в attrs, если они были в запросе,
        # так как они write_only=False (по умолчанию) или write_only=True, но required=False.
        # Если они write_only=True и required=False, они могут быть None в attrs.
        existing_type = attrs.get('existing_content_type')
        existing_id = attrs.get('existing_content_id')

        if is_update and not final_material_data_payload and not (existing_type and existing_id):
            return attrs # Обновляем только order или ничего специфичного для контента

        if item_type not in CONTENT_TYPE_MAP:
            raise serializers.ValidationError({"item_type": f"Недопустимый тип элемента: {item_type}"})

        has_new_content_data = bool(final_material_data_payload)
        has_existing_link_data = bool(existing_type and existing_id)

        if has_new_content_data and has_existing_link_data:
            raise serializers.ValidationError("Укажите либо данные для нового контента, либо ссылку на существующий, но не оба.")

        if not has_new_content_data and not has_existing_link_data:
            if not is_update:
                raise serializers.ValidationError("Необходимо указать данные для нового контента или ссылку на существующий.")
        
        if has_existing_link_data:
             if not existing_type or not existing_id: # Это условие избыточно, если has_existing_link_data уже true
                 pass # Оставим для ясности, но проверка выше уже это покрывает
             if existing_type != item_type:
                 raise serializers.ValidationError({"existing_content_type": f"Тип существующего контента '{existing_type}' не совпадает с типом элемента '{item_type}'."})
             model_class = CONTENT_TYPE_MAP[existing_type]['model']
             if not model_class.objects.filter(pk=existing_id).exists():
                 raise serializers.ValidationError({"existing_content_id": f"Контент типа '{existing_type}' с ID {existing_id} не найден."})

        if has_new_content_data:
            material_serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
            material_serializer_instance = material_serializer_class(data=final_material_data_payload, context=self.context)
            try:
                material_serializer_instance.is_valid(raise_exception=True)
                # Сохраняем валидированные данные материала для использования в create/update
                attrs['validated_material_data'] = material_serializer_instance.validated_data 
            except serializers.ValidationError as e:
                raise serializers.ValidationError({'content_material_data': e.detail})
        
        # Удаляем исходное поле 'content_data' из attrs, так как оно было write_only
        # и мы его уже обработали. Это предотвратит его передачу в self.create или self.update.
        # Поля existing_content_type и existing_content_id также write_only, DRF должен сам их убрать
        # из validated_data перед вызовом create/update, если они не являются полями модели.
        attrs.pop('content_data', None)
        attrs.pop('existing_content_type', None)
        attrs.pop('existing_content_id', None)
        
        return attrs

    def create(self, validated_data):
        # validated_data здесь уже содержит:
        # - section (из perform_create -> save)
        # - order (из perform_create -> save)
        # - item_type (из запроса)
        # - content_type (ContentType инстанс, из perform_create -> save)
        # - object_id (PK материала, из perform_create -> save)
        # - И НЕ должно содержать 'validated_material_data', 'content_data', 'existing_*'
        
        # 'validated_material_data' мы добавили в attrs в validate, его нужно извлечь,
        # оно не является полем SectionItem.
        validated_data.pop('validated_material_data', None) 
        
        # Поля content_data, existing_content_type, existing_content_id
        # уже должны были быть удалены в `validate` или отфильтрованы DRF, так как они write_only.
        # На всякий случай, если они как-то просочились:
        validated_data.pop('content_data', None)
        validated_data.pop('existing_content_type', None)
        validated_data.pop('existing_content_id', None)

        try:
            section_item = SectionItem.objects.create(**validated_data)
        except Exception as e:
            # Это место, где может возникнуть TypeError, если в validated_data все еще есть лишние ключи.
            # Или IntegrityError, если UNIQUE constraint не был разрешен ранее.
            # print(f"Error in SectionItemSerializer.create with validated_data: {validated_data}") # DEBUG
            # print(f"Exception: {e}") # DEBUG
            raise # Переподнимаем исключение, чтобы оно было обработано выше
        return section_item

    def update(self, instance, validated_data):
        # Аналогично create, нужно очистить validated_data от 'validated_material_data'
        validated_data.pop('validated_material_data', None)
        validated_data.pop('content_data', None)
        validated_data.pop('existing_content_type', None)
        validated_data.pop('existing_content_id', None)
        
        # kwargs для instance.save() или SectionItem.objects.filter(pk=instance.pk).update(**kwargs)
        # validated_data будет содержать 'order' (если пришел), 'item_type' (если пришел)
        # content_type и object_id передаются через kwargs в perform_update -> save
        
        # Обновляем поля GenericForeignKey, если они переданы в validated_data из save()
        instance.content_type = validated_data.get('content_type', instance.content_type)
        instance.object_id = validated_data.get('object_id', instance.object_id)
        
        # Обновляем остальные поля
        instance.item_type = validated_data.get('item_type', instance.item_type)
        instance.order = validated_data.get('order', instance.order)
        # section обычно не меняется при обновлении элемента
        
        instance.save()
        return instance

class SectionSerializer(serializers.ModelSerializer):
    """Сериализатор для разделов урока."""
    is_completed = serializers.SerializerMethodField()
    items = SectionItemSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = [
            'id', 'lesson', 'title', 'order',
            'created_at', 'updated_at', 'is_completed', 'items'
        ]
        read_only_fields = ['lesson', 'created_at', 'updated_at', 'is_completed', 'items']

    def get_is_completed(self, obj):
        """Проверяет, завершил ли текущий пользователь этот раздел."""
        user = self.context['request'].user
        if user and user.is_authenticated:
            return SectionCompletion.objects.filter(section=obj, student=user).exists()
        return False

    def validate_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Порядок не может быть отрицательным.")
        return value


class LessonListSerializer(serializers.ModelSerializer):
    """Сериализатор для списка уроков."""
    created_by_name = serializers.ReadOnlyField(source='created_by.username')
    section_count = serializers.SerializerMethodField()
    course_id = serializers.ReadOnlyField(source='course.id') # Добавим ID курса

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'cover_image', 'course_id',
            'created_by_name', 'created_at', 'updated_at', 'section_count'
        ]

    def get_section_count(self, obj):
        """Возвращает количество разделов в уроке."""
        return obj.sections.count()


class LessonDetailSerializer(serializers.ModelSerializer):
    """Сериализатор для детальной информации об уроке."""
    created_by = UserSerializer(read_only=True)
    sections = SectionSerializer(many=True, read_only=True)
    is_completed = serializers.SerializerMethodField()
    course_id = serializers.ReadOnlyField(source='course.id')

    class Meta:
        model = Lesson
        fields = [
            'id', 'course_id', 'title', 'cover_image',
            'created_by', 'created_at', 'updated_at', 'sections', 'is_completed'
        ]
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'sections', 'is_completed', 'course_id')


    def get_is_completed(self, obj):
        """Проверяет, завершил ли текущий пользователь этот урок."""
        user = self.context['request'].user
        if user and user.is_authenticated:
            return LessonCompletion.objects.filter(lesson=obj, student=user).exists()
        return False

class SectionCompletionSerializer(serializers.ModelSerializer):
    """Сериализатор для отметки о завершении раздела."""
    student_details = UserSerializer(source='student', read_only=True)
    section_details = SectionSerializer(source='section', read_only=True)

    class Meta:
        model = SectionCompletion
        fields = ['id', 'section', 'section_details', 'student', 'student_details', 'completed_at']
        read_only_fields = ['id', 'student', 'student_details', 'section_details', 'completed_at']

class LessonCompletionSerializer(serializers.ModelSerializer):
    """Сериализатор для отметки о завершении урока."""
    student_details = UserSerializer(source='student', read_only=True)
    lesson_details = LessonListSerializer(source='lesson', read_only=True)

    class Meta:
        model = LessonCompletion
        fields = ['id', 'lesson', 'lesson_details', 'student', 'student_details', 'completed_at']
        read_only_fields = ['id', 'student', 'student_details', 'lesson_details', 'completed_at']