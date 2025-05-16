from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import viewsets, status, filters, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from .models import Lesson, Section, SectionCompletion, LessonCompletion, SectionItem
from .serializers import (
    LessonListSerializer, LessonDetailSerializer, SectionSerializer,
    SectionCompletionSerializer, LessonCompletionSerializer
)
from .permissions import LessonPermission, SectionPermission, CanComplete, IsCourseStaffOrAdmin, CanViewLessonOrSectionContent
from kei_backend.utils import send_to_kafka
from .serializers import SectionItemSerializer, CONTENT_TYPE_MAP
from course_service.models import Course


class LessonPagination(PageNumberPagination):
    page_size = 4
    page_size_query_param = 'page_size'
    max_page_size = 100


class LessonViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, LessonPermission]
    pagination_class = LessonPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title',]
    ordering_fields = ['created_at', 'title', 'updated_at']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return LessonListSerializer
        return LessonDetailSerializer

    def get_queryset(self):
        user = self.request.user
        course_pk = self.kwargs.get('course_pk')

        if not course_pk:
            return Lesson.objects.none()

        course = get_object_or_404(Course, pk=course_pk)
        if not CanViewLessonOrSectionContent().has_object_permission(self.request, self, course): 
             self.permission_denied(self.request, message="У вас нет доступа к этому курсу.")

        queryset = Lesson.objects.filter(course=course)\
                                 .select_related('created_by')\
                                 .prefetch_related('sections') 


        return queryset

    def perform_create(self, serializer):
        course_pk = self.kwargs.get('course_pk')
        course = get_object_or_404(Course, pk=course_pk)

        if not IsCourseStaffOrAdmin().has_object_permission(self.request, self, course):
             self.permission_denied(self.request, message="У вас нет прав на добавление уроков в этот курс.")

        serializer.save(created_by=self.request.user, course=course)

    def perform_update(self, serializer):
        instance = serializer.instance
        new_course_id = self.request.data.get('course_id')
        if new_course_id and instance.course_id != int(new_course_id):
             raise serializers.ValidationError({"course_id": "Изменение курса урока не разрешено."})
        serializer.save()

    # Action для получения статуса завершения урока текущим пользователем
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, CanViewLessonOrSectionContent])
    def completion_status(self, request, pk=None):
        lesson = self.get_object() # Права на просмотр проверены CanViewLessonOrSectionContent
        user = request.user
        try:
            completion = LessonCompletion.objects.get(lesson=lesson, student=user)
            serializer = LessonCompletionSerializer(completion, context={'request': request})
            return Response({"completed": True, "details": serializer.data})
        except LessonCompletion.DoesNotExist:
            return Response({"completed": False})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanComplete])
    def complete(self, request, pk=None):
        lesson = self.get_object()
        student = request.user

        total_sections = lesson.sections.count()
        completed_sections = SectionCompletion.objects.filter(
            section__lesson=lesson,
            student=student
        ).count()

        if total_sections == 0:
            pass
        elif total_sections != completed_sections:
            return Response(
                {"error": "Не все разделы урока завершены."},
                status=status.HTTP_400_BAD_REQUEST
            )

        completion, created = LessonCompletion.objects.get_or_create(
            lesson=lesson,
            student=student,
        )

        if created:
            send_to_kafka('progress_events', {
                'type': 'lesson_completed',
                'user_id': student.id,
                'lesson_id': lesson.id,
                'course_id': lesson.course_id,
                'timestamp': timezone.now().isoformat()
            })
            serializer = LessonCompletionSerializer(completion, context={'request': request})
            return Response(
                {"success": "Урок успешно завершен.", "details": serializer.data},
                status=status.HTTP_201_CREATED
            )
        else:
            serializer = LessonCompletionSerializer(completion, context={'request': request})
            return Response(
                {"message": "Урок уже был завершен ранее.", "details": serializer.data},
                status=status.HTTP_200_OK
            )


class SectionViewSet(viewsets.ModelViewSet):
    """
    ViewSet для Разделов Урока.
    Доступ к разделам определяется доступом к родительскому уроку.
    """
    serializer_class = SectionSerializer
    permission_classes = [IsAuthenticated, SectionPermission]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['order', 'created_at', 'title']
    ordering = ['order']

    def get_queryset(self):
        lesson_pk = self.kwargs.get('lesson_pk')

        if not lesson_pk:
            return Section.objects.none()

        lesson = get_object_or_404(Lesson, pk=lesson_pk)


        if not CanViewLessonOrSectionContent().has_object_permission(self.request, self, lesson):
             self.permission_denied(self.request, message="У вас нет доступа к этому уроку.")

        return Section.objects.filter(lesson=lesson)

    def perform_create(self, serializer):
        lesson_pk = self.kwargs.get('lesson_pk')
        lesson = get_object_or_404(Lesson, pk=lesson_pk)

        if not IsCourseStaffOrAdmin().has_object_permission(self.request, self, lesson):
             self.permission_denied(self.request, message="У вас нет прав на добавление разделов в этот урок.")

        max_order = Section.objects.filter(lesson=lesson).aggregate(Max('order'))['order__max']
        current_order = (max_order or 0) + 1
        serializer.save(lesson=lesson, order=current_order)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, CanViewLessonOrSectionContent])
    def completion_status(self, request, lesson_pk=None, pk=None):
        section = self.get_object()
        user = request.user
        try:
            completion = SectionCompletion.objects.get(section=section, student=user)
            serializer = SectionCompletionSerializer(completion, context={'request': request})
            return Response({"completed": True, "details": serializer.data})
        except SectionCompletion.DoesNotExist:
            return Response({"completed": False})


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanComplete]) # Завершать могут записанные студенты
    def complete(self, request, lesson_pk=None, pk=None):
        section = self.get_object()
        student = request.user
        lesson = section.lesson

        with transaction.atomic():
            completion, created = SectionCompletion.objects.get_or_create(
                section=section,
                student=student,
            )

            if created:
                send_to_kafka('progress_events', {
                    'type': 'section_completed',
                    'user_id': student.id,
                    'section_id': section.id,
                    'lesson_id': lesson.id,
                    'course_id': lesson.course_id,
                    'timestamp': timezone.now().isoformat()
                })

                total_sections = lesson.sections.count()
                completed_sections_count = SectionCompletion.objects.filter(
                    section__lesson=lesson,
                    student=student
                ).count()

                lesson_completion_created = False
                if total_sections > 0 and total_sections == completed_sections_count:
                    lesson_completion, lesson_created = LessonCompletion.objects.get_or_create(
                         lesson=lesson,
                         student=student
                    )
                    if lesson_created:
                        lesson_completion_created = True
                        # Отправляем событие о завершении урока
                        send_to_kafka('progress_events', {
                            'type': 'lesson_completed',
                            'user_id': student.id,
                            'lesson_id': lesson.id,
                            'course_id': lesson.course_id,
                            'timestamp': timezone.now().isoformat()
                        })

                serializer = SectionCompletionSerializer(completion, context={'request': request})
                response_data = {"success": "Раздел успешно завершен.", "details": serializer.data}
                if lesson_completion_created:
                    response_data["lesson_completed"] = True

                return Response(response_data, status=status.HTTP_201_CREATED)

            else:
                serializer = SectionCompletionSerializer(completion, context={'request': request})
                return Response(
                    {"message": "Раздел уже был завершен ранее.", "details": serializer.data},
                    status=status.HTTP_200_OK
                )
                
    @action(detail=False, methods=['post'], url_path='reorder', permission_classes=[IsAuthenticated, IsCourseStaffOrAdmin])
    def reorder_sections(self, request, lesson_pk=None, course_pk=None): # course_pk будет из URL
        """
        Изменяет порядок разделов в указанном уроке.
        Ожидает POST-запрос с телом: [{"id": section_id1, "order": new_order1}, {"id": section_id2, "order": new_order2}, ...]
        """
        lesson = get_object_or_404(Lesson, pk=lesson_pk, course_id=course_pk)

        data = request.data
        if not isinstance(data, list):
            return Response({"error": "Ожидается список объектов с 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)

        updates_map = {}  # {section_id: new_order}
        new_orders_set = set()
        section_ids_from_payload = []

        for item in data:
            if not isinstance(item, dict) or 'id' not in item or 'order' not in item:
                return Response({"error": "Каждый элемент должен быть словарем с 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                section_id = int(item.get('id'))
                new_order = int(item.get('order'))
            except (ValueError, TypeError):
                 return Response({"error": "ID и order должны быть целыми числами."}, status=status.HTTP_400_BAD_REQUEST)

            if new_order < 0:
                return Response({"error": "Порядок (order) не может быть отрицательным."}, status=status.HTTP_400_BAD_REQUEST)

            if new_order in new_orders_set:
                return Response({"error": f"Порядок {new_order} указан более одного раза в запросе."}, status=status.HTTP_400_BAD_REQUEST)
            
            new_orders_set.add(new_order)
            section_ids_from_payload.append(section_id)
            updates_map[section_id] = new_order
        
        sections_to_update_qs = Section.objects.filter(lesson=lesson, id__in=section_ids_from_payload)
        
        if sections_to_update_qs.count() != len(section_ids_from_payload):
            found_ids = set(sections_to_update_qs.values_list('id', flat=True))
            missing_ids = [sid for sid in section_ids_from_payload if sid not in found_ids]
            return Response(
                {"error": "Одна или несколько указанных секций не найдены или не принадлежат этому уроку.",
                 "missing_section_ids": missing_ids}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        conflicting_sections_qs = Section.objects.filter(lesson=lesson, order__in=new_orders_set)\
                                                 .exclude(id__in=section_ids_from_payload)
        if conflicting_sections_qs.exists():
            conflict_details = {s.id: s.order for s in conflicting_sections_qs}
            return Response(
                {"error": "Некоторые из новых порядков уже заняты другими разделами этого урока (которые не были включены в текущий запрос на изменение порядка).",
                 "conflicts_with_other_sections": conflict_details},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                
                sections_to_update_list = list(sections_to_update_qs) 

                max_existing_order = Section.objects.filter(lesson=lesson).aggregate(max_o=models.Max('order'))['max_o'] or 0
                temp_order_start = -1 * (max_existing_order + len(sections_to_update_list) + 10) # Добавим запас

                for i, section_instance in enumerate(sections_to_update_list):
                    section_instance.order = temp_order_start - i # Уникальный отрицательный order
                    section_instance.save(update_fields=['order'])
                
                for section_id, target_order in updates_map.items():
                    section_to_set_final_order = Section.objects.get(pk=section_id, lesson=lesson) # Получаем актуальный инстанс
                    section_to_set_final_order.order = target_order
                    section_to_set_final_order.save(update_fields=['order'])
            
            updated_sections_qs = Section.objects.filter(lesson=lesson).order_by('order')
            serializer = self.get_serializer(updated_sections_qs, many=True, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except IntegrityError as e:
            return Response({"error": f"Ошибка целостности базы данных при обновлении порядка: {e}. Пожалуйста, проверьте данные."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": f"Произошла непредвиденная ошибка: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class SectionItemViewSet(viewsets.ModelViewSet):
    """ViewSet для управления элементами раздела (SectionItem)."""
    serializer_class = SectionItemSerializer
    permission_classes = [IsAuthenticated] # Добавляем кастомный пермишен ниже

    def get_queryset(self):
        """Фильтруем элементы по ID раздела из URL."""
        section_pk = self.kwargs.get('section_pk')
        if not section_pk:
            return SectionItem.objects.none()

        # Проверяем доступ к родительскому разделу (и уроку/курсу)
        section = get_object_or_404(
            Section.objects.select_related('lesson__course'), # Для проверки прав
            pk=section_pk,
            # Добавляем проверку из kwargs родительских роутеров
            lesson_id=self.kwargs.get('lesson_pk'),
            lesson__course_id=self.kwargs.get('course_pk')
        )
        # Используем CanViewLessonOrSectionContent для проверки доступа к разделу
        if not CanViewLessonOrSectionContent().has_object_permission(self.request, self, section):
            self.permission_denied(self.request, message="У вас нет доступа к этому разделу.")

        return SectionItem.objects.filter(section=section).select_related('content_type') # Добавляем content_type для оптимизации

    def get_permissions(self):
        """Устанавливаем права: Просмотр для тех, кто видит раздел, Запись - для персонала курса."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # Для записи нужны права персонала
            return [IsAuthenticated(), IsCourseStaffOrAdmin()] # IsCourseStaffOrAdmin проверит права на раздел/урок/курс
        # Для чтения (list, retrieve)
        return [IsAuthenticated(), CanViewLessonOrSectionContent()] # Проверит доступ к разделу

    def _get_section(self):
        """Вспомогательная функция для получения объекта Section."""
        return get_object_or_404(
            Section,
            pk=self.kwargs['section_pk'],
            lesson_id=self.kwargs.get('lesson_pk'),
            lesson__course_id=self.kwargs.get('course_pk')
        )

    def perform_create(self, serializer):
        section = self._get_section()
        # Права уже проверены в get_permissions -> IsCourseStaffOrAdmin

        # Определяем порядок
        max_order = SectionItem.objects.filter(section=section).aggregate(Max('order'))['order__max']
        current_order = (max_order or 0) + 1
        # Позволяем переопределить порядок из запроса, если нужно
        order = serializer.validated_data.get('order', current_order)

        item_type = serializer.validated_data['item_type']
        content_data = serializer.validated_data.get('validated_content_data') # Используем валидированные данные
        existing_type = serializer.validated_data.get('existing_content_type')
        existing_id = serializer.validated_data.get('existing_content_id')

        content_object = None
        content_type = None

        try:
            with transaction.atomic():
                if content_data:
                     # Создаем новый контент в material_service
                    model_class = CONTENT_TYPE_MAP[item_type]['model']
                    serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                    # Используем сериализатор для создания объекта
                    # Передаем request в контекст для perform_create вложенного сериализатора (если он использует created_by)
                    context = {'request': self.request}
                    content_serializer = serializer_class(data=content_data, context=context)
                    content_serializer.is_valid(raise_exception=True) # Должно быть валидно после validate
                    # Если у вложенного сериализатора нет perform_create, user не установится
                    # Можно передать user явно: content_object = content_serializer.save(created_by=self.request.user)
                    content_object = content_serializer.save()
                    content_type = ContentType.objects.get_for_model(model_class)

                elif existing_type and existing_id:
                     # Связываем с существующим
                    model_class = CONTENT_TYPE_MAP[existing_type]['model']
                    content_object = model_class.objects.get(pk=existing_id) # Уже проверено в validate
                    content_type = ContentType.objects.get_for_model(model_class)
                else:
                    # Эта ситуация не должна возникать из-за validate
                    raise ValueError("Ошибка в логике валидации: нет данных для контента.")

                # Создаем SectionItem
                serializer.save(
                    section=section,
                    order=order,
                    content_type=content_type,
                    object_id=content_object.pk,
                    # Убираем лишние поля из validated_data перед сохранением
                    content_data=None,
                    existing_content_type=None,
                    existing_content_id=None
                )
        except Exception as e:
             # Логирование ошибки e
             # Если контент был создан, но SectionItem нет - откатываем транзакцию
             raise serializers.ValidationError(f"Не удалось создать элемент раздела: {e}")


    def perform_update(self, serializer):
        # Логика обновления может быть сложной, если разрешено менять тип контента
        # или переключаться между созданием нового и связью с существующим.
        # Пока реализуем простое обновление order и опционально - контента.

        section = self._get_section() # Родительский раздел не меняется
        item_type = serializer.validated_data.get('item_type', self.get_object().item_type) # Тип тоже обычно не меняется
        content_data = serializer.validated_data.get('validated_content_data')
        existing_type = serializer.validated_data.get('existing_content_type')
        existing_id = serializer.validated_data.get('existing_content_id')

        current_instance = serializer.instance
        content_object = current_instance.content_object
        content_type = current_instance.content_type

        try:
            with transaction.atomic():
                # Обновление связанного контента (если передан content_data)
                if content_data and item_type in CONTENT_TYPE_MAP:
                    serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                    context = {'request': self.request}
                    content_serializer = serializer_class(instance=content_object, data=content_data, partial=True, context=context)
                    if content_serializer.is_valid(raise_exception=True):
                        content_object = content_serializer.save() # Обновляем контент

                # Смена связи на существующий контент (если переданы existing_*)
                elif existing_type and existing_id:
                     if existing_type == item_type: # Убедимся еще раз
                         model_class = CONTENT_TYPE_MAP[existing_type]['model']
                         new_content_object = model_class.objects.get(pk=existing_id)
                         new_content_type = ContentType.objects.get_for_model(model_class)
                         # Обновляем GenericForeignKey в SectionItem
                         current_instance.content_type = new_content_type
                         current_instance.object_id = new_content_object.pk
                         content_object = new_content_object # Обновляем для сохранения
                         content_type = new_content_type
                     else:
                          raise serializers.ValidationError("Несоответствие типа при смене связи контента.")

                # Сохраняем сам SectionItem (обновляем order и, возможно, GenericForeignKey)
                serializer.save(
                     content_object=content_object, # Передаем объект для обновления FK
                     content_type=content_type,
                     object_id=content_object.pk,
                     # Убираем лишние поля
                     content_data=None,
                     existing_content_type=None,
                     existing_content_id=None
                )
        except Exception as e:
             raise serializers.ValidationError(f"Не удалось обновить элемент раздела: {e}")
