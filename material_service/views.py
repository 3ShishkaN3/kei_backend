from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets, status, mixins, parsers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from .models import *
from .serializers import *
from .permissions import IsAdminOrStaffWriteOrReadOnly, CanSubmitTest
from kei_backend.utils import send_to_kafka
from lesson_service.models import SectionItem
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
    queryset = Test.objects.prefetch_related( # Prefetch для оптимизации сериализатора
        'mcq_options', 'matching_pairs', 'matching_distractors'
    ).select_related(
        'free_text_question', 'word_order_sentence', 'pronunciation_question',
        'spelling_question', 'attached_image', 'attached_audio', 'created_by'
    ).all()
    serializer_class = TestSerializer
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser] # Для возможных файлов в тесте


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
        permission_classes=[IsAuthenticated, CanSubmitTest], # Права на отправку
        serializer_class=TestSubmissionInputSerializer, # Сериализатор для входных данных
        parser_classes=[parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser] # Для файлов ответов
    )
    @action( # Атрибуты action остаются
        detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanSubmitTest],
        serializer_class=TestSubmissionInputSerializer,
        parser_classes=[parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]
    )
    def submit(self, request, pk=None):
        test = self.get_object()
        student = request.user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        answers_data = validated_data.get('answers')
        section_item_id = validated_data.get('section_item_id')

        try:
            section_item = SectionItem.objects.select_related('section__lesson__course').get(
                pk=section_item_id,
                content_type__model=test._meta.model_name,
                object_id=test.pk
            )
        except SectionItem.DoesNotExist:
             return Response({"error": "Связь теста с элементом урока не найдена или некорректна."}, status=status.HTTP_400_BAD_REQUEST)

        # Определяем начальный статус и статус после возможной автопроверки
        initial_status = 'submitted'
        final_status = 'submitted' # По умолчанию
        test_type = test.test_type

        # Типы, требующие ручной проверки
        if test_type in ['free-text', 'pronunciation', 'spelling']:
            initial_status = 'grading_pending'
            final_status = 'grading_pending'
        # Типы, где фронтенд гарантирует правильность
        elif test_type in ['word-order', 'matching']:
             initial_status = 'auto_passed' # Сразу считаем пройденным
             final_status = 'auto_passed'
        # Типы с возможной автопроверкой (MCQ)
        elif test_type in ['mcq-single', 'mcq-multi']:
             # Здесь можно добавить логику автопроверки MCQ, если нужно
             # и установить final_status в 'auto_passed' или 'auto_failed'
             # Пока оставляем 'submitted', проверка будет внешней
             pass


        try:
            with transaction.atomic():
                submission = TestSubmission.objects.create(
                    test=test,
                    student=student,
                    section_item=section_item,
                    status=initial_status # Используем начальный статус
                )

                # Сохранение ответов (логика остается почти той же)
                if test_type in ['mcq-single', 'mcq-multi']:
                    option_ids = answers_data.get('selected_option_ids', [])
                    mcq_answer = MCQSubmissionAnswer.objects.create(submission=submission)
                    options = MCQOption.objects.filter(id__in=option_ids, test=test)
                    mcq_answer.selected_options.set(options)

                elif test_type == 'free-text':
                    FreeTextSubmissionAnswer.objects.create(
                        submission=submission,
                        answer_text=answers_data.get('answer_text', '')
                    )
                elif test_type == 'word-order':
                    WordOrderSubmissionAnswer.objects.create(
                        submission=submission,
                        submitted_order_words=answers_data.get('submitted_order_words', [])
                    )
                elif test_type == 'matching':
                    match_answers = answers_data.get('answers', [])
                    pairs_to_create = []
                    valid_pair_ids = set(test.matching_pairs.values_list('id', flat=True))
                    for ans in match_answers:
                         pair_id = ans.get('matching_pair_id')
                         if pair_id in valid_pair_ids:
                             pairs_to_create.append(
                                 MatchingSubmissionAnswer(
                                     submission=submission,
                                     matching_pair_id=pair_id,
                                     submitted_answer_text=ans.get('submitted_answer_text', '')
                                 )
                             )
                    if pairs_to_create:
                        MatchingSubmissionAnswer.objects.bulk_create(pairs_to_create)

                elif test_type == 'pronunciation':
                    audio_file = request.FILES.get('submitted_audio_file')
                    if audio_file:
                         PronunciationSubmissionAnswer.objects.create(submission=submission, submitted_audio_file=audio_file)
                    else: raise ValueError("Аудиофайл не найден.")

                elif test_type == 'spelling':
                    image_file = request.FILES.get('submitted_image_file')
                    if image_file:
                         SpellingSubmissionAnswer.objects.create(submission=submission, submitted_image_file=image_file)
                    else: raise ValueError("Изображение не найдено.")

                if final_status != initial_status:
                     submission.status = final_status
                     submission.save(update_fields=['status'])

        except Exception as e:
            return Response({"error": f"Ошибка при сохранении ответа: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            lesson = section_item.section.lesson
            course = lesson.course
            kafka_data = {
                'type': 'test_submitted',
                'user_id': student.id,
                'submission_id': submission.id,
                'test_id': test.id,
                'test_type': test.test_type,
                'section_item_id': section_item.id,
                'section_id': section_item.section.id,
                'lesson_id': lesson.id,
                'course_id': course.id,
                'timestamp': submission.submitted_at.isoformat(),
                'status': submission.status, # Отправляем финальный статус
            }
            send_to_kafka('progress_events', kafka_data)
        except Exception as e:
             print(f"Error sending Kafka event for submission {submission.id}: {e}")

        submission_detail_serializer = TestSubmissionDetailSerializer(submission, context=self.get_serializer_context())
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