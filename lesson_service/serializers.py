import json
from rest_framework import serializers
import requests
from .models import Lesson, Section, SectionCompletion, LessonCompletion, SectionItem
from auth_service.serializers import UserSerializer
from material_service.serializers import (
    TextMaterialSerializer, ImageMaterialSerializer, AudioMaterialSerializer,
    VideoMaterialSerializer, DocumentMaterialSerializer, TestSerializer,
    TestSubmissionDetailSerializer
)
from material_service.models import (
    TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial, Test,
    TestSubmission
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
    is_completed = serializers.SerializerMethodField(read_only=True)
    content_data = serializers.JSONField(write_only=True, required=False, allow_null=True,
                                         help_text="JSON-объект с данными для создания нового контента (текста, теста и т.д.) или метаданные для файлов.")
    existing_content_type = serializers.CharField(write_only=True, required=False, allow_null=True, help_text="Тип существующего контента (напр., 'text', 'test')")
    existing_content_id = serializers.IntegerField(write_only=True, required=False, allow_null=True, help_text="ID существующего контента")

    class Meta:
        model = SectionItem
        fields = [
            'id', 'section', 'order', 'item_type',
            'content_details', 'is_completed',
            'content_data', 'existing_content_type', 'existing_content_id',
            'created_at', 'updated_at',
        ]
        read_only_fields = ('section', 'created_at', 'updated_at')
        extra_kwargs = {
            'item_type': {'required': True, 'allow_blank': False},
            'order': {'required': False},
        }

    def get_content_details(self, obj):
        content_object = obj.content_object
        if content_object:
            item_type = obj.item_type
            if item_type in CONTENT_TYPE_MAP:
                serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                context = self.context
                if 'request' not in context and hasattr(self, 'root') and hasattr(self.root, 'context'):
                    context['request'] = self.root.context.get('request')
                elif 'request' not in context:
                     context['request'] = None

                try:
                    data = serializer_class(content_object, context=context).data
                    if item_type == 'test' and context.get('request') and hasattr(context['request'], 'user'):
                        user = context['request'].user
                        user_settings = getattr(user, 'settings', None)
                        show_answers = True
                        try:
                            if user.is_authenticated:
                                if user_settings is not None:
                                    show_answers = getattr(user_settings, 'show_test_answers', True)
                                else:
                                    show_answers = True
                            else:
                                show_answers = True
                        except Exception:
                            show_answers = True

                        if show_answers:
                            try:
                                last_submission = (
                                    TestSubmission.objects.filter(test=content_object, student=user, section_item=obj)
                                    .order_by('-submitted_at')
                                    .first()
                                )
                                if last_submission is not None:
                                    submission_serializer = TestSubmissionDetailSerializer(
                                        last_submission,
                                        context={'request': context.get('request')}
                                    )
                                    data['student_submission_details'] = submission_serializer.data
                            except Exception:
                                pass
                    return data
                except Exception as e:
                    print(f"Error serializing content for item {obj.id} (type: {item_type}): {e}")
                    return {"error": "Could not serialize content details."}
        return None

    def get_is_completed(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return False
        try:
            base_url = request.build_absolute_uri('/api/v1/progress/')
            headers = {}
            csrf = request.COOKIES.get('csrftoken')
            if csrf:
                headers['X-CSRFTOKEN'] = csrf
            cache = self.context.setdefault('_progress_cache', {})
            if obj.item_type == 'test':
                lesson_id = obj.section.lesson.id
                tests_cache = cache.setdefault('tests_by_lesson', {})
                mapping = tests_cache.get(lesson_id)
                if mapping is None:
                    tests_url = f"{base_url}tests/?lesson_id={lesson_id}"
                    resp = requests.get(tests_url, headers=headers, cookies=request.COOKIES, timeout=3)
                    if resp.status_code != 200:
                        tests_cache[lesson_id] = {}
                        return False
                    data = resp.json()
                    results = data.get('results', data if isinstance(data, list) else [])
                    mapping = {int(e.get('test_id', 0)): (e.get('status') or '').lower() for e in results}
                    tests_cache[lesson_id] = mapping
                status = mapping.get(int(obj.object_id))
                return status == 'passed'
            section_cache = cache.setdefault('sections', {})
            s_entry = section_cache.get(obj.section.id)
            if s_entry is None:
                section_url = f"{base_url}sections/?section_id={obj.section.id}"
                s_resp = requests.get(section_url, headers=headers, cookies=request.COOKIES, timeout=3)
                if s_resp.status_code != 200:
                    section_cache[obj.section.id] = None
                    return False
                s_data = s_resp.json()
                s_results = s_data.get('results', s_data if isinstance(s_data, list) else [])
                if not s_results:
                    section_cache[obj.section.id] = None
                    return False
                s_entry = s_results[0]
                section_cache[obj.section.id] = s_entry
            completion = float(s_entry.get('completion_percentage', 0))
            if completion >= 99.5:
                return True
            if s_entry.get('total_tests', 0) == 0 and s_entry.get('is_visited'):
                return True
            return False
        except Exception:
            return False

    def validate(self, attrs):
        raw_initial_data = self.initial_data
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
        final_material_data_payload.update(files_for_material)

        existing_type = attrs.get('existing_content_type')
        existing_id = attrs.get('existing_content_id')

        if is_update and not final_material_data_payload and not (existing_type and existing_id):
            return attrs

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
             if not existing_type or not existing_id:
                 pass
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
                attrs['validated_material_data'] = material_serializer_instance.validated_data 
            except serializers.ValidationError as e:
                raise serializers.ValidationError({'content_material_data': e.detail})
        


        attrs.pop('content_data', None)
        attrs.pop('existing_content_type', None)
        attrs.pop('existing_content_id', None)
        
        return attrs

    def create(self, validated_data):
        

        validated_data.pop('validated_material_data', None) 
        

        validated_data.pop('content_data', None)
        validated_data.pop('existing_content_type', None)
        validated_data.pop('existing_content_id', None)

        try:
            section_item = SectionItem.objects.create(**validated_data)
        except Exception as e:
                    raise
        return section_item

    def update(self, instance, validated_data):
        validated_data.pop('validated_material_data', None)
        validated_data.pop('content_data', None)
        validated_data.pop('existing_content_type', None)
        validated_data.pop('existing_content_id', None)
        

        
        instance.content_type = validated_data.get('content_type', instance.content_type)
        instance.object_id = validated_data.get('object_id', instance.object_id)
        
        instance.item_type = validated_data.get('item_type', instance.item_type)
        instance.order = validated_data.get('order', instance.order)
        
        instance.save()
        return instance

class SectionSerializer(serializers.ModelSerializer):
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
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return False
        try:
            cache = self.context.setdefault('_progress_cache', {})
            section_cache = cache.setdefault('sections', {})
            entry = section_cache.get(obj.id)
            if entry is None:
                base_url = request.build_absolute_uri('/api/v1/progress/')
                url = f"{base_url}sections/?section_id={obj.id}"
                headers = {}
                csrf = request.COOKIES.get('csrftoken')
                if csrf:
                    headers['X-CSRFTOKEN'] = csrf
                resp = requests.get(url, headers=headers, cookies=request.COOKIES, timeout=3)
                if resp.status_code != 200:
                    section_cache[obj.id] = None
                    return False
                data = resp.json()
                results = data.get('results', data if isinstance(data, list) else [])
                if not results:
                    section_cache[obj.id] = None
                    return False
                entry = results[0]
                section_cache[obj.id] = entry
            completion = float(entry.get('completion_percentage', 0))
            if completion >= 99.5:
                return True
            if entry.get('completed_at'):
                return True
            if entry.get('total_tests', 0) == 0 and entry.get('is_visited'):
                return True
            return False
        except Exception:
            return False

    def validate_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Порядок не может быть отрицательным.")
        return value


class LessonListSerializer(serializers.ModelSerializer):
    created_by_name = serializers.ReadOnlyField(source='created_by.username')
    section_count = serializers.SerializerMethodField()
    course_id = serializers.ReadOnlyField(source='course.id')
    completion_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'cover_image', 'course_id',
            'created_by_name', 'created_at', 'updated_at', 'section_count',
            'completion_percentage'
        ]

    def get_section_count(self, obj):
        return obj.sections.count()

    def get_completion_percentage(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return 0
        try:
            base_url = request.build_absolute_uri('/api/v1/progress/')
            url = f"{base_url}lessons/?lesson_id={obj.id}"
            headers = {}
            csrf = request.COOKIES.get('csrftoken')
            if csrf:
                headers['X-CSRFTOKEN'] = csrf
            resp = requests.get(url, headers=headers, cookies=request.COOKIES, timeout=3)
            if resp.status_code != 200:
                return 0
            data = resp.json()
            results = data.get('results', data if isinstance(data, list) else [])
            if not results:
                return 0
            entry = results[0]
            return float(entry.get('completion_percentage', 0))
        except Exception:
            return 0


class LessonDetailSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    sections = SectionSerializer(many=True, read_only=True)
    is_completed = serializers.SerializerMethodField()
    course_id = serializers.ReadOnlyField(source='course.id')
    completion_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            'id', 'course_id', 'title', 'cover_image',
            'created_by', 'created_at', 'updated_at', 'sections', 'is_completed',
            'completion_percentage'
        ]
        read_only_fields = ('created_by', 'created_at', 'updated_at', 'sections', 'is_completed', 'course_id', 'completion_percentage')


    def get_is_completed(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return False
        try:
            base_url = request.build_absolute_uri('/api/v1/progress/')
            url = f"{base_url}lessons/?lesson_id={obj.id}"
            headers = {}
            csrf = request.COOKIES.get('csrftoken')
            if csrf:
                headers['X-CSRFTOKEN'] = csrf
            resp = requests.get(url, headers=headers, cookies=request.COOKIES, timeout=3)
            if resp.status_code != 200:
                return False
            data = resp.json()
            results = data.get('results', data if isinstance(data, list) else [])
            if not results:
                return False
            entry = results[0]
            completion = float(entry.get('completion_percentage', 0))
            if completion >= 99.5:
                return True
            if entry.get('completed_at'):
                return True
            return False
        except Exception:
            return False

    def get_completion_percentage(self, obj):
        request = self.context.get('request')
        if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
            return 0
        try:
            base_url = request.build_absolute_uri('/api/v1/progress/')
            url = f"{base_url}lessons/?lesson_id={obj.id}"
            headers = {}
            csrf = request.COOKIES.get('csrftoken')
            if csrf:
                headers['X-CSRFTOKEN'] = csrf
            resp = requests.get(url, headers=headers, cookies=request.COOKIES, timeout=3)
            if resp.status_code != 200:
                return 0
            data = resp.json()
            results = data.get('results', data if isinstance(data, list) else [])
            if not results:
                return 0
            entry = results[0]
            return float(entry.get('completion_percentage', 0))
        except Exception:
            return 0

class SectionCompletionSerializer(serializers.ModelSerializer):
    student_details = UserSerializer(source='student', read_only=True)
    section_details = SectionSerializer(source='section', read_only=True)

    class Meta:
        model = SectionCompletion
        fields = ['id', 'section', 'section_details', 'student', 'student_details', 'completed_at']
        read_only_fields = ['id', 'student', 'student_details', 'section_details', 'completed_at']

class LessonCompletionSerializer(serializers.ModelSerializer):
    student_details = UserSerializer(source='student', read_only=True)
    lesson_details = LessonListSerializer(source='lesson', read_only=True)

    class Meta:
        model = LessonCompletion
        fields = ['id', 'lesson', 'lesson_details', 'student', 'student_details', 'completed_at']
        read_only_fields = ['id', 'student', 'student_details', 'lesson_details', 'completed_at']