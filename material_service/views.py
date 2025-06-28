from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import viewsets, status, mixins, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import (
    TextMaterial, ImageMaterial, AudioMaterial, VideoMaterial, DocumentMaterial,
    Test, MCQOption, FreeTextQuestion, WordOrderSentence, MatchingPair,
    PronunciationQuestion, SpellingQuestion, TestSubmission,
    MCQSubmissionAnswer, FreeTextSubmissionAnswer, WordOrderSubmissionAnswer,
    DragDropSubmissionAnswer, PronunciationSubmissionAnswer, SpellingSubmissionAnswer
)
from .serializers import (
    TextMaterialSerializer, ImageMaterialSerializer, AudioMaterialSerializer,
    VideoMaterialSerializer, DocumentMaterialSerializer, TestSerializer,
    TestSubmissionInputSerializer, TestSubmissionDetailSerializer, TestSubmissionListSerializer
)
from .permissions import IsAdminOrStaffWriteOrReadOnly, CanSubmitTest
from kei_backend.utils import send_to_kafka
from lesson_service.models import SectionItem
from course_service.models import CourseTeacher, CourseAssistant
from rest_framework import filters

# --- ViewSets для CRUD материалов и тестов (Админка/Персонал) ---

class BaseMaterialViewSet(viewsets.ModelViewSet):
    """Базовый ViewSet для материалов с общими правами."""
    permission_classes = [IsAuthenticated, IsAdminOrStaffWriteOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class TextMaterialViewSet(BaseMaterialViewSet):
    queryset = TextMaterial.objects.all()
    serializer_class = TextMaterialSerializer

class ImageMaterialViewSet(BaseMaterialViewSet):
    queryset = ImageMaterial.objects.all()
    serializer_class = ImageMaterialSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser] # Для загрузки файлов

class AudioMaterialViewSet(BaseMaterialViewSet):
    queryset = AudioMaterial.objects.all()
    serializer_class = AudioMaterialSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

class VideoMaterialViewSet(BaseMaterialViewSet):
    queryset = VideoMaterial.objects.all()
    serializer_class = VideoMaterialSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

class DocumentMaterialViewSet(BaseMaterialViewSet):
    queryset = DocumentMaterial.objects.all()
    serializer_class = DocumentMaterialSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

class TestViewSet(BaseMaterialViewSet):
    """ViewSet для CRUD тестов и для отправки ответов студентами."""
    queryset = Test.objects.prefetch_related(
        'mcq_options',       # ManyToMany или обратный ForeignKey к MCQOption
        'drag_drop_slots',   # Новое имя для бывших matching_pairs (связанных с MatchingPair)
        # 'matching_distractors' - удалено, так как модель удалена
    ).select_related(
        'free_text_question',       # OneToOneField
        'word_order_sentence_details', # ИЗМЕНЕНО: related_name для WordOrderSentence
        'pronunciation_question',   # OneToOneField
        'spelling_question',        # OneToOneField
        'attached_image',           # ForeignKey
        'attached_audio',           # ForeignKey
        'created_by'                # ForeignKey
    ).all()
    serializer_class = TestSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser] # Для возможных файлов в тесте


    def _perform_auto_check(self, test_instance, answers_data_from_json, submission_instance):
        """
        Performs auto-checking for MCQ, Word Order, and Drag Drop tests.
        Updates submission_instance.status and submission_instance.score.
        """
        test_type = test_instance.test_type
        score = 0.0
        is_passed = False

        if test_type in ['mcq-single', 'mcq-multi']:
            selected_option_ids = set(answers_data_from_json.get('selected_option_ids', []))
            correct_options = MCQOption.objects.filter(test=test_instance, is_correct=True)
            correct_option_ids = set(correct_options.values_list('id', flat=True))

            if test_type == 'mcq-single':
                if len(selected_option_ids) == 1 and list(selected_option_ids)[0] in correct_option_ids:
                    score = 1.0
                    is_passed = True
                else:
                    score = 0.0
                    is_passed = False
            elif test_type == 'mcq-multi':
                # Calculate score for multi-choice: proportion of correctly selected options
                # and no incorrect options selected.
                total_correct_options = len(correct_option_ids)
                if total_correct_options == 0: # No correct answers defined, consider it passed if no options selected
                    score = 1.0
                    is_passed = True
                else:
                    correctly_selected_count = len(selected_option_ids.intersection(correct_option_ids))
                    incorrectly_selected_count = len(selected_option_ids - correct_option_ids)
                    
                    if incorrectly_selected_count > 0: # If any incorrect option is selected, it's a fail
                        score = 0.0
                        is_passed = False
                    elif correctly_selected_count == total_correct_options: # All correct options selected
                        score = 1.0
                        is_passed = True
                    else: # Partially correct, but no incorrect selected
                        score = correctly_selected_count / total_correct_options
                        is_passed = False # Consider partially correct as not passed for now, can be adjusted

        elif test_type == 'word-order':
            submitted_order_words = answers_data_from_json.get('submitted_order_words', [])
            correct_ordered_texts = test_instance.word_order_sentence_details.correct_ordered_texts

            # Normalize lists for comparison (e.g., strip whitespace, convert to lowercase if needed)
            # User specified "облачка" with same text are identical, so direct comparison of lists of strings is fine.
            if submitted_order_words == correct_ordered_texts:
                score = 1.0
                is_passed = True
            else:
                score = 0.0
                is_passed = False

        elif test_type == 'drag-and-drop':
            submitted_slot_answers = answers_data_from_json.get('answers', [])
            total_slots = test_instance.drag_drop_slots.count()
            correct_slots_count = 0

            valid_slots_map = {slot.id: slot for slot in test_instance.drag_drop_slots.all()}

            for ans_item_data in submitted_slot_answers:
                slot_id = ans_item_data.get('slot_id')
                dropped_text = ans_item_data.get('dropped_option_text')

                if slot_id in valid_slots_map:
                    slot_instance = valid_slots_map[slot_id]
                    if slot_instance.correct_answer_text == dropped_text:
                        correct_slots_count += 1
            
            if total_slots > 0:
                score = correct_slots_count / total_slots
                is_passed = (score == 1.0)
            else: # No slots defined, consider it passed
                score = 1.0
                is_passed = True

        # Update submission instance
        submission_instance.score = score
        if is_passed:
            submission_instance.status = 'auto_passed'
        else:
            submission_instance.status = 'auto_failed'
        submission_instance.save(update_fields=['score', 'status'])


    def get_serializer_context(self):
        # Передаем тест в контекст сериализатора для валидации ответов
        context = super().get_serializer_context()
        if self.action == 'submit':
             try:
                 # Получаем тест из URL (pk передается в action)
                 test_instance = self.get_object()
                 context['test'] = test_instance
             except Exception:
                 # Обработка случая, если тест не найден до вызова сериализатора
                 pass
        # Передаем request для валидации файлов и построения URL
        context['request'] = self.request
        return context

    @action(
        detail=True,
        methods=['post'],
        permission_classes=[IsAuthenticated, CanSubmitTest],  # Права на отправку
        serializer_class=TestSubmissionInputSerializer,  # Сериализатор для входных данных
        parser_classes=[parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]  # Для файлов ответов
    )
    def submit(self, request, pk=None):
        """
        Принимает ответы студента на тест, сохраняет их и отправляет событие в Kafka.
        """
        test_instance = self.get_object()  # Получаем тест по pk из URL
        student = request.user
        
        # Формируем контекст для входного сериализатора, добавляя текущий тест
        serializer_context = self.get_serializer_context()
        serializer_context['test'] = test_instance 
        
        input_serializer = self.get_serializer(data=request.data, context=serializer_context)
        input_serializer.is_valid(raise_exception=True)
        
        validated_input_data = input_serializer.validated_data
        # answers_data_from_json - это уже провалидированный словарь ответов (структура зависит от test_type)
        answers_data_from_json = validated_input_data.get('answers') 
        section_item_id = validated_input_data.get('section_item_id')

        # Проверяем, что SectionItem существует и связан с этим тестом
        try:
            section_item = SectionItem.objects.select_related('section__lesson__course').get(
                pk=section_item_id,
                content_type__model=Test._meta.model_name,
                object_id=test_instance.pk
            )
        except SectionItem.DoesNotExist:
             return Response(
                 {"detail": "Связь теста с элементом урока не найдена или некорректна."}, 
                 status=status.HTTP_400_BAD_REQUEST
             )

        # Определяем начальный статус отправки в зависимости от типа теста
        submission_status = 'submitted'  # Статус по умолчанию
        if test_instance.test_type in ['free-text', 'pronunciation', 'spelling']:
            submission_status = 'grading_pending'  # Требуют ручной проверки
        # Для MCQ, WordOrder, Drag-and-Drop оставляем 'submitted', 
        # предполагая, что оценка и фидбек придут от другого сервиса или позже.

        submission_instance = None  # Для использования в блоке Kafka

        try:
            with transaction.atomic():
                # 1. Создаем основную запись TestSubmission
                submission_instance = TestSubmission.objects.create(
                    test=test_instance, 
                    student=student, 
                    section_item=section_item, 
                    status=submission_status,
                    submitted_at=timezone.now()  # Явно устанавливаем время
                )

                # 2. Сохраняем специфичные ответы для каждого типа теста
                test_type = test_instance.test_type

                if test_type in ['mcq-single', 'mcq-multi']:
                    option_ids = answers_data_from_json.get('selected_option_ids', [])
                    mcq_answer_obj = MCQSubmissionAnswer.objects.create(submission=submission_instance)
                    # Проверяем, что все ID опций принадлежат данному тесту
                    valid_options = MCQOption.objects.filter(id__in=option_ids, test=test_instance)
                    if len(option_ids) > 0 and valid_options.count() != len(set(option_ids)):  # set для уникальных ID
                        raise serializers.ValidationError("Одна или несколько выбранных опций не принадлежат этому тесту.")
                    mcq_answer_obj.selected_options.set(valid_options)

                elif test_type == 'free-text':
                    FreeTextSubmissionAnswer.objects.create(
                        submission=submission_instance,
                        answer_text=answers_data_from_json.get('answer_text', '')
                    )
                elif test_type == 'word-order':
                    WordOrderSubmissionAnswer.objects.create(
                        submission=submission_instance,
                        submitted_order_words=answers_data_from_json.get('submitted_order_words', [])
                    )
                elif test_type == 'drag-and-drop':
                    submitted_slot_answers = answers_data_from_json.get('answers', [])
                    answers_to_create_for_drag_drop = []
                    
                    valid_slots_map = {slot.id: slot for slot in test_instance.drag_drop_slots.all()}
                    options_pool_set = set(test_instance.draggable_options_pool or [])

                    for ans_item_data in submitted_slot_answers:
                        slot_id = ans_item_data.get('slot_id')
                        dropped_text = ans_item_data.get('dropped_option_text')

                        if slot_id not in valid_slots_map:
                            raise serializers.ValidationError(f"Слот с ID {slot_id} не найден для этого теста.")
                        if dropped_text not in options_pool_set:
                            raise serializers.ValidationError(f"Облачко с текстом '{dropped_text}' отсутствует в наборе вариантов для этого теста.")
                        
                        slot_instance = valid_slots_map[slot_id]
                        is_item_correct = (slot_instance.correct_answer_text == dropped_text)
                        
                        answers_to_create_for_drag_drop.append(
                            DragDropSubmissionAnswer(
                                submission=submission_instance,
                                slot=slot_instance,
                                dropped_option_text=dropped_text,
                                is_correct=is_item_correct 
                            )
                        )
                    if answers_to_create_for_drag_drop:
                        DragDropSubmissionAnswer.objects.bulk_create(answers_to_create_for_drag_drop)
                
                elif test_type == 'pronunciation':
                    # Файлы извлекаются из request.FILES, так как TestSubmissionInputSerializer
                    # пометил их как write_only=True и они не будут в validated_input_data['answers']
                    audio_file = request.FILES.get('submitted_audio_file')
                    if not audio_file:
                         raise serializers.ValidationError({"submitted_audio_file": "Аудиофайл не был предоставлен для теста на произношение."})
                    PronunciationSubmissionAnswer.objects.create(
                        submission=submission_instance, 
                        submitted_audio_file=audio_file
                    )
                
                elif test_type == 'spelling':
                    image_file = request.FILES.get('submitted_image_file')
                    if not image_file:
                         raise serializers.ValidationError({"submitted_image_file": "Изображение не было предоставлено для теста на правописание."})
                    SpellingSubmissionAnswer.objects.create(
                        submission=submission_instance, 
                        submitted_image_file=image_file
                    )
                
                # Perform auto-check for relevant test types
                if test_type in ['mcq-single', 'mcq-multi', 'word-order', 'drag-and-drop']:
                    self._perform_auto_check(test_instance, answers_data_from_json, submission_instance)
                
                # If the test type requires manual grading, set status to grading_pending
                if test_type in ['free-text', 'pronunciation', 'spelling']:
                    submission_instance.status = 'grading_pending'
                    submission_instance.save(update_fields=['status'])

        except serializers.ValidationError:
            raise  # Переподнимаем ошибки валидации, чтобы DRF вернул 400
        except IntegrityError as e:  # Например, если UNIQUE constraint на ответы (маловероятно здесь)
             return Response({"detail": f"Ошибка целостности данных при сохранении ответа: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": f"Произошла внутренняя ошибка при сохранении ответа: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if submission_instance:
            try:
                lesson = section_item.section.lesson
                course = lesson.course
                kafka_data = {
                    'type': 'test_submitted', 
                    'user_id': student.id, 
                    'submission_id': submission_instance.id,
                    'test_id': test_instance.id, 
                    'test_title': test_instance.title,
                    'test_type': test_instance.test_type,
                    'section_item_id': section_item.id,
                    'section_id': section_item.section.id,
                    'section_title': section_item.section.title,
                    'lesson_id': lesson.id,
                    'lesson_title': lesson.title,
                    'course_id': course.id,
                    'course_title': course.title,
                    'timestamp': submission_instance.submitted_at.isoformat(), 
                    'status': submission_instance.status,
                }
                send_to_kafka('progress_events', kafka_data)
            except Exception as e:
                 print(f"Error sending Kafka event for submission {submission_instance.id}: {e}")

        response_serializer_context = self.get_serializer_context()
        response_serializer_context['test'] = test_instance
        
        submission_detail_serializer = TestSubmissionDetailSerializer(submission_instance, context=response_serializer_context)
        return Response(submission_detail_serializer.data, status=status.HTTP_201_CREATED)




class TestSubmissionViewSet(mixins.ListModelMixin,
                            mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.OrderingFilter] # Добавляем фильтры, если нужно
    ordering_fields = ['submitted_at', 'status', 'score']
    ordering = ['-submitted_at']


    def get_queryset(self):
        user = self.request.user
        # Базовый queryset с оптимизацией запросов
        queryset = TestSubmission.objects.select_related(
            'test', 'student', 'section_item__section__lesson__course' # Включаем курс
        ).prefetch_related(
            'mcq_answers__selected_options', 'matching_answers__matching_pair',
            'free_text_answer', 'word_order_answer', 'pronunciation_answer', 'spelling_answer'
        ).all()

        if user.role in ['admin', 'teacher', 'assistant']:
            # Фильтрация для персонала
            course_id = self.request.query_params.get('course_id')
            lesson_id = self.request.query_params.get('lesson_id')
            section_id = self.request.query_params.get('section_id')
            test_id = self.request.query_params.get('test_id')
            student_id = self.request.query_params.get('student_id') # Фильтр по студенту
            status_filter = self.request.query_params.get('status') # Фильтр по статусу

            if user.role == 'admin':
                # Админ видит все, но может фильтровать
                pass
            else:
                 # Учитель/Ассистент видят только отправки по своим курсам
                 teacher_courses = CourseTeacher.objects.filter(teacher=user).values_list('course_id', flat=True)
                 assistant_courses = CourseAssistant.objects.filter(assistant=user).values_list('course_id', flat=True)
                 managed_course_ids = set(list(teacher_courses) + list(assistant_courses))
                 # Фильтруем по ID курсов, полученных через связи
                 queryset = queryset.filter(section_item__section__lesson__course_id__in=managed_course_ids)

            # Применяем дополнительные фильтры из query params
            if course_id:
                queryset = queryset.filter(section_item__section__lesson__course_id=course_id)
            if lesson_id:
                 queryset = queryset.filter(section_item__section__lesson_id=lesson_id)
            if section_id:
                 queryset = queryset.filter(section_item__section_id=section_id)
            if test_id:
                 queryset = queryset.filter(test_id=test_id)
            if student_id:
                 queryset = queryset.filter(student_id=student_id)
            if status_filter:
                 queryset = queryset.filter(status=status_filter)

        else:
            # Студент видит только свои отправки
            queryset = queryset.filter(student=user)
            # Студент также может фильтровать по курсу/уроку/тесту
            course_id = self.request.query_params.get('course_id')
            lesson_id = self.request.query_params.get('lesson_id')
            test_id = self.request.query_params.get('test_id')
            if course_id:
                queryset = queryset.filter(section_item__section__lesson__course_id=course_id)
            if lesson_id:
                 queryset = queryset.filter(section_item__section__lesson_id=lesson_id)
            if test_id:
                 queryset = queryset.filter(test_id=test_id)

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return TestSubmissionListSerializer
        return TestSubmissionDetailSerializer
