from rest_framework import serializers
from .models import Lesson, Section, SectionCompletion, LessonCompletion, SectionItem
from auth_service.serializers import UserSerializer
from django.contrib.contenttypes.models import ContentType
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
    """Сериализатор для элемента раздела, с динамической обработкой контента."""
    # Поле для чтения деталей контента
    content_details = serializers.SerializerMethodField(read_only=True)
    # Поле для записи данных нового контента (write_only)
    content_data = serializers.JSONField(write_only=True, required=False, allow_null=True,
                                         help_text="JSON объект с данными для создания нового контента (текста, теста и т.д.)")
    # Поля для связи с существующим контентом (write_only)
    existing_content_type = serializers.CharField(write_only=True, required=False, allow_null=True, help_text="Тип существующего контента (напр., 'text', 'test')")
    existing_content_id = serializers.IntegerField(write_only=True, required=False, allow_null=True, help_text="ID существующего контента")


    class Meta:
        model = SectionItem
        fields = [
            'id', 'section', 'order', 'item_type',
            'content_details', # Для чтения
            'content_data', 'existing_content_type', 'existing_content_id', # Для записи
            'created_at', 'updated_at',
            # Скрываем поля GenericForeignKey из прямого доступа API
            # 'content_type', 'object_id',
        ]
        read_only_fields = ('section', 'created_at', 'updated_at') # section устанавливается во ViewSet
        extra_kwargs = {
             # Убедимся, что item_type обязателен при создании
            'item_type': {'required': True, 'allow_blank': False},
             # order может быть не обязателен, установим во ViewSet
            'order': {'required': False},
        }

    def get_content_details(self, obj):
        """Динамически сериализует связанный контент."""
        content_object = obj.content_object
        if content_object:
            item_type = obj.item_type
            if item_type in CONTENT_TYPE_MAP:
                serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                context = self.context
                 # Добавляем 'request' в контекст, если его нет (важно для URL файлов)
                if 'request' not in context:
                    context['request'] = None # Или можно попытаться получить из self.root?
                try:
                    return serializer_class(content_object, context=context).data
                except Exception as e:
                    print(f"Error serializing content for item {obj.id}: {e}")
                    return None # Или вернуть индикатор ошибки
        return None

    def validate(self, attrs):
        """Проверяем логику записи: либо content_data, либо existing_*, но не оба."""
        content_data = attrs.get('content_data')
        existing_type = attrs.get('existing_content_type')
        existing_id = attrs.get('existing_content_id')
        item_type = attrs.get('item_type') # item_type должен быть всегда

        # При обновлении (self.instance существует) можно не передавать контент
        is_update = self.instance is not None
        if is_update and not content_data and not existing_type and not existing_id:
             # Если обновляется только order, например
            return attrs

        # Проверка item_type
        if item_type not in CONTENT_TYPE_MAP:
            raise serializers.ValidationError({"item_type": f"Недопустимый тип элемента: {item_type}"})

        if content_data and (existing_type or existing_id):
            raise serializers.ValidationError("Укажите либо 'content_data' для создания нового контента, либо 'existing_content_type' и 'existing_content_id' для связи с существующим, но не оба.")

        if not content_data and not (existing_type and existing_id):
            # При создании (not is_update) контент обязателен
            if not is_update:
                raise serializers.ValidationError("Необходимо указать либо 'content_data' для создания нового контента, либо 'existing_content_type' и 'existing_content_id' для связи с существующим.")

        if existing_type or existing_id:
             if not existing_type or not existing_id:
                 raise serializers.ValidationError("Для связи с существующим контентом необходимо указать и 'existing_content_type', и 'existing_content_id'.")
             if existing_type != item_type:
                 raise serializers.ValidationError({"existing_content_type": f"Тип существующего контента '{existing_type}' не совпадает с типом элемента '{item_type}'."})
             # Проверяем существование объекта в material_service
             if existing_type in CONTENT_TYPE_MAP:
                 model_class = CONTENT_TYPE_MAP[existing_type]['model']
                 if not model_class.objects.filter(pk=existing_id).exists():
                     raise serializers.ValidationError({"existing_content_id": f"Контент типа '{existing_type}' с ID {existing_id} не найден."})
             else: # На всякий случай
                  raise serializers.ValidationError({"existing_content_type": "Неизвестный тип существующего контента."})

        if content_data:
            # Валидируем content_data с помощью соответствующего сериализатора
             if item_type in CONTENT_TYPE_MAP:
                 serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                 # Передаем данные для валидации
                 content_serializer = serializer_class(data=content_data, context=self.context)
                 try:
                     content_serializer.is_valid(raise_exception=True)
                     # Сохраняем валидированные данные обратно для использования в perform_create/update
                     attrs['validated_content_data'] = content_serializer.validated_data
                 except serializers.ValidationError as e:
                      # Перехватываем ошибку валидации контента и поднимаем ее как ошибку поля content_data
                     raise serializers.ValidationError({'content_data': e.detail})
             else: # На всякий случай
                 raise serializers.ValidationError({"item_type": "Не удается найти сериализатор для валидации content_data."})

        return attrs

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