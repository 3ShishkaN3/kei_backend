from django.shortcuts import get_object_or_404
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError, models
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
from .permissions import LessonPermission, SectionPermission, CanCompleteItems, IsCourseStaffOrAdmin, CanViewLessonOrSectionContent
from kei_backend.utils import send_to_kafka
from .serializers import SectionItemSerializer, CONTENT_TYPE_MAP
from course_service.models import Course

class LessonPagination(PageNumberPagination):
    page_size = 4
    page_size_query_param = 'page_size'
    max_page_size = 1000


class LessonViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, LessonPermission]
    pagination_class = LessonPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['title', 'table_of_contents', 'dictionary_entries__term', 'dictionary_entries__reading']
    ordering = ['order', 'id']

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
                                 .prefetch_related('sections')\
                                 .order_by('order', 'id')
        return queryset

    def retrieve(self, request, *args, **kwargs):
        """Переопределяем retrieve для просмотра урока"""
        return super().retrieve(request, *args, **kwargs)

    def perform_create(self, serializer):
        course_pk = self.kwargs.get('course_pk')
        course = get_object_or_404(Course, pk=course_pk)

        if not IsCourseStaffOrAdmin().has_object_permission(self.request, self, course):
             self.permission_denied(self.request, message="У вас нет прав на добавление уроков в этот курс.")

        max_order = Lesson.objects.filter(course=course).aggregate(Max('order'))['order__max']
        next_order = (max_order or 0) + 1 if max_order is not None else 0

        serializer.save(created_by=self.request.user, course=course, order=next_order)

    def perform_update(self, serializer):
        instance = serializer.instance
        new_course_id = self.request.data.get('course_id')
        if new_course_id and instance.course_id != int(new_course_id):
             raise serializers.ValidationError({"course_id": "Изменение курса урока не разрешено."})
        serializer.save()

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, CanViewLessonOrSectionContent])
    def completion_status(self, request, pk=None):
        lesson = self.get_object()
        user = request.user
        try:
            completion = LessonCompletion.objects.get(lesson=lesson, student=user)
            serializer = LessonCompletionSerializer(completion, context={'request': request})
            return Response({"completed": True, "details": serializer.data})
        except LessonCompletion.DoesNotExist:
            return Response({"completed": False})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanCompleteItems])
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
            success = send_to_kafka('progress_events', {
                'type': 'lesson_completed',
                'user_id': student.id,
                'lesson_id': lesson.id,
                'course_id': lesson.course_id,
                'timestamp': timezone.now().isoformat()
            })
            if not success:
                print(f"Не удалось отправить событие lesson_completed для урока {lesson.id}")
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

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def all_simple(self, request):
        """
        Возвращает упрощенный список всех уроков (id, title, course_title)
        для использования в селекторах админки/редактора достижений.
        Игнорирует фильтрацию по курсу.
        """
        if not (request.user.is_staff or getattr(request.user, 'role', '') == 'admin'):
             return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        lessons = Lesson.objects.all().select_related('course').values('id', 'title', 'course__title')
        return Response(list(lessons))

    @action(detail=False, methods=['post'], url_path='reorder', permission_classes=[IsAuthenticated, IsCourseStaffOrAdmin])
    def reorder_lessons(self, request, course_pk=None):
        course = get_object_or_404(Course, pk=course_pk)

        data = request.data
        if not isinstance(data, list):
            return Response({"error": "Ожидается список объектов с 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)

        updates_map = {}
        new_orders_set = set()
        lesson_ids_from_payload = []

        for item in data:
            try:
                lesson_id = int(item.get('id'))
                new_order = int(item.get('order'))
            except (ValueError, TypeError, AttributeError):
                 return Response({"error": "Каждый элемент должен быть словарем с целыми 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)

            if new_order < 0:
                return Response({"error": "Порядок (order) не может быть отрицательным."}, status=status.HTTP_400_BAD_REQUEST)
            if new_order in new_orders_set:
                return Response({"error": f"Порядок {new_order} дублируется в запросе."}, status=status.HTTP_400_BAD_REQUEST)
            
            new_orders_set.add(new_order)
            lesson_ids_from_payload.append(lesson_id)
            updates_map[lesson_id] = new_order
        
        lessons_to_update_qs = Lesson.objects.filter(course=course, id__in=lesson_ids_from_payload)
        
        if lessons_to_update_qs.count() != len(set(lesson_ids_from_payload)):
            return Response({"error": "Один или несколько уроков не найдены в данном курсе."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                max_current = Lesson.objects.filter(course=course).aggregate(Max('order'))['order__max'] or 0
                temp_offset = max_current + 1000
                
                lessons_instances = list(lessons_to_update_qs)
                for i, obj in enumerate(lessons_instances):
                    obj.order = temp_offset + i
                    obj.save(update_fields=['order'])
                
                for obj in lessons_instances:
                    obj.order = updates_map[obj.id]
                    obj.save(update_fields=['order'])
            
            return Response({"status": "Порядок уроков обновлен"}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    


class SectionViewSet(viewsets.ModelViewSet):
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

    def retrieve(self, request, *args, **kwargs):
        """Переопределяем retrieve для просмотра секции"""
        return super().retrieve(request, *args, **kwargs)

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


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanCompleteItems])
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
                success = send_to_kafka('progress_events', {
                    'type': 'section_completed',
                    'user_id': student.id,
                    'section_id': section.id,
                    'lesson_id': lesson.id,
                    'course_id': lesson.course_id,
                    'timestamp': timezone.now().isoformat()
                })
                if not success:
                    print(f"Не удалось отправить событие section_completed для секции {section.id}")

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
                        success = send_to_kafka('progress_events', {
                            'type': 'lesson_completed',
                            'user_id': student.id,
                            'lesson_id': lesson.id,
                            'course_id': lesson.course_id,
                            'timestamp': timezone.now().isoformat()
                        })
                        if not success:
                            print(f"Не удалось отправить событие lesson_completed для урока {lesson.id}")

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
    def reorder_sections(self, request, lesson_pk=None, course_pk=None):
        lesson = get_object_or_404(Lesson, pk=lesson_pk, course_id=course_pk)

        data = request.data
        if not isinstance(data, list):
            return Response({"error": "Ожидается список объектов с 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)

        updates_map = {}
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
                sections_to_update_qs = Section.objects.filter(lesson=lesson, id__in=section_ids_from_payload) 
                
                if sections_to_update_qs.count() != len(section_ids_from_payload): 
                    found_ids = set(sections_to_update_qs.values_list('id', flat=True))
                    missing_ids = [sid for sid in section_ids_from_payload if sid not in found_ids]
                    return Response(
                        {"error": "Одна или несколько указанных секций не найдены или не принадлежат этому уроку (проверка перед транзакцией).",
                         "missing_section_ids": missing_ids},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                max_current_order_obj = Section.objects.filter(lesson=lesson).aggregate(max_val=Max('order'))
                max_current_order = max_current_order_obj['max_val'] if max_current_order_obj['max_val'] is not None else -1 
                max_payload_order = 0
                if new_orders_set: 
                    max_payload_order = max(new_orders_set)

                temp_order_start = max(max_current_order, max_payload_order) + len(section_ids_from_payload) + 10 

                sections_being_updated_instances = list(sections_to_update_qs) 

                for i, section_instance in enumerate(sections_being_updated_instances):
                    section_instance.order = temp_order_start + i 
                    section_instance.save(update_fields=['order'])
                

                for section_id_to_update, target_order in updates_map.items():
                    section_to_set_final_order = next((s for s in sections_being_updated_instances if s.id == section_id_to_update), None)
                    if section_to_set_final_order:
                        section_to_set_final_order.order = target_order
                        section_to_set_final_order.save(update_fields=['order'])
                    else:
                        raise ValueError(f"Логическая ошибка: не найден инстанс для section_id {section_id_to_update}")
            
            updated_sections_qs = Section.objects.filter(lesson=lesson).order_by('order')
            serializer = self.get_serializer(updated_sections_qs, many=True, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        except IntegrityError as e:
            return Response({"error": f"Ошибка целостности базы данных при обновлении порядка: {e}. Пожалуйста, проверьте данные."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"error": f"Произошла непредвиденная ошибка: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
class SectionItemViewSet(viewsets.ModelViewSet):
    serializer_class = SectionItemSerializer

    def get_queryset(self):
        section_pk = self.kwargs.get('section_pk')
        lesson_pk = self.kwargs.get('lesson_pk')
        course_pk = self.kwargs.get('course_pk')

        if not all([section_pk, lesson_pk, course_pk]):
            return SectionItem.objects.none()

        section = get_object_or_404(
            Section.objects.select_related('lesson__course'),
            pk=section_pk,
            lesson_id=lesson_pk,
            lesson__course_id=course_pk
        )
        
        if not CanViewLessonOrSectionContent().has_object_permission(self.request, self, section.lesson.course):
            self.permission_denied(self.request, message="У вас нет доступа к этому разделю.")
        
        return SectionItem.objects.filter(section=section).select_related('content_type').order_by('order')

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'reorder_items']:
            return [IsAuthenticated(), IsCourseStaffOrAdmin()]
        return [IsAuthenticated(), CanViewLessonOrSectionContent()]

    def _get_section_for_write_operations(self):
        section_pk = self.kwargs.get('section_pk')
        lesson_pk = self.kwargs.get('lesson_pk')
        course_pk = self.kwargs.get('course_pk')

        section = get_object_or_404(
            Section.objects.select_related('lesson__course'),
            pk=section_pk,
            lesson_id=lesson_pk,
            lesson__course_id=course_pk
        )
        
        if not IsCourseStaffOrAdmin().has_object_permission(self.request, self, section.lesson.course):
            self.permission_denied(self.request, message="У вас нет прав на изменение содержимого этого раздела.")
        return section

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanViewLessonOrSectionContent])
    def viewed(self, request, course_pk=None, lesson_pk=None, section_pk=None, pk=None):
        """Отметить элемент раздела как просмотренный (для нетестовых материалов).
        Паблишит событие material_viewed в Kafka. Идемпотентно на стороне консюмера.
        """
        section = get_object_or_404(
            Section.objects.select_related('lesson__course'),
            pk=section_pk,
            lesson_id=lesson_pk,
            lesson__course_id=course_pk
        )
        if not CanViewLessonOrSectionContent().has_object_permission(self.request, self, section.lesson.course):
            self.permission_denied(self.request, message="У вас нет доступа к этому разделу.")

        item = get_object_or_404(
            SectionItem.objects.select_related('section'),
            pk=pk,
            section=section
        )
        if item.item_type == 'test':
            return Response({"detail": "Для тестов просмотр не фиксируется этим методом."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        success = send_to_kafka('progress_events', {
            'type': 'material_viewed',
            'user_id': user.id,
            'section_item_id': item.id,
            'section_id': item.section.id,
            'lesson_id': item.section.lesson.id,
            'course_id': item.section.lesson.course.id,
            'item_type': item.item_type,
            'timestamp': timezone.now().isoformat()
        })
        if not success:
            print(f"Не удалось отправить событие material_viewed для элемента {item.id}")

        return Response({"success": True}, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        section = self._get_section_for_write_operations()
        
        item_type = serializer.validated_data['item_type']

        material_data_for_creation_or_update = serializer.validated_data.get('validated_material_data') 
        
        existing_type = serializer.initial_data.get('existing_content_type')
        existing_id = serializer.initial_data.get('existing_content_id')

        content_object = None
        content_type_for_item = None
        
        try:
            with transaction.atomic():
                if material_data_for_creation_or_update:
                    if item_type == 'test':
                        test_serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']

                        test_serializer_instance = test_serializer_class(data=material_data_for_creation_or_update, context=serializer.context)
                        if test_serializer_instance.is_valid(raise_exception=True):
                            content_object = test_serializer_instance.save() 
                        else:
                            raise serializers.ValidationError({"detail": "Ошибка валидации данных теста."})
                    else:
                        model_class = CONTENT_TYPE_MAP[item_type]['model']
                        content_object = model_class.objects.create(**material_data_for_creation_or_update)
                    
                    content_type_for_item = ContentType.objects.get_for_model(content_object.__class__)

                elif existing_type and existing_id:
                    model_class = CONTENT_TYPE_MAP[existing_type]['model']
                    content_object = get_object_or_404(model_class, pk=existing_id)
                    content_type_for_item = ContentType.objects.get_for_model(model_class)
                else:
                    raise serializers.ValidationError(
                        {"detail": "Не предоставлены данные для создания или связи контента."}
                    )

                max_order_obj = SectionItem.objects.filter(section=section).aggregate(max_val=Max('order'))
                max_order_val = max_order_obj['max_val']
                new_item_order = (max_order_val + 1) if max_order_val is not None else 0
                
                serializer.save(
                    section=section,
                    order=new_item_order,
                    content_type=content_type_for_item,
                    object_id=content_object.pk
                )
        except IntegrityError as e:
            if 'UNIQUE constraint failed' in str(e):
                raise serializers.ValidationError(
                    {"detail": "Ошибка уникальности при сохранении элемента (возможно, конфликт порядка)."}
                )
            else:
                raise serializers.ValidationError({"detail": f"Ошибка базы данных при создании элемента: {e}"})
        except Exception as e:
            # import traceback; traceback.print_exc();
            raise serializers.ValidationError({"detail": f"Не удалось создать элемент раздела: {e}"})

    def perform_update(self, serializer):
        current_instance = serializer.instance # SectionItem
        section = current_instance.section 
        
        if not IsCourseStaffOrAdmin().has_object_permission(self.request, self, section.lesson.course):
            self.permission_denied(self.request, message="У вас нет прав на изменение этого элемента.")

        material_data_for_update = serializer.validated_data.get('validated_material_data')
        item_type = serializer.validated_data.get('item_type', current_instance.item_type)
        
        existing_type = serializer.initial_data.get('existing_content_type')
        existing_id = serializer.initial_data.get('existing_content_id')

        update_kwargs_for_section_item_save = {}

        try:
            with transaction.atomic():
                content_object_to_update_or_replace = current_instance.content_object
                new_content_type_for_item = current_instance.content_type
                new_object_id_for_item = current_instance.object_id

                if material_data_for_update:
                    current_content_model_class = content_object_to_update_or_replace.__class__ if content_object_to_update_or_replace else None
                    target_material_model_class = CONTENT_TYPE_MAP[item_type]['model']

                    if current_content_model_class != target_material_model_class or not content_object_to_update_or_replace:
                        # if content_object_to_update_or_replace:
                        #     pass
                        
                        if item_type == 'test':
                            test_serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                            new_test_serializer = test_serializer_class(data=material_data_for_update, context=serializer.context)
                            new_test_serializer.is_valid(raise_exception=True)
                            content_object_to_update_or_replace = new_test_serializer.save()
                        else:
                            content_object_to_update_or_replace = target_material_model_class.objects.create(**material_data_for_update)
                        
                        new_content_type_for_item = ContentType.objects.get_for_model(target_material_model_class)
                        new_object_id_for_item = content_object_to_update_or_replace.pk
                    else:
                        if item_type == 'test':
                            test_serializer_class = CONTENT_TYPE_MAP[item_type]['serializer']
                            test_serializer_instance = test_serializer_class(
                                instance=content_object_to_update_or_replace, 
                                data=material_data_for_update, 
                                partial=True, 
                                context=serializer.context
                            )
                            if test_serializer_instance.is_valid(raise_exception=True):
                                content_object_to_update_or_replace = test_serializer_instance.save()
                        else:
                            for key, value in material_data_for_update.items():
                                setattr(content_object_to_update_or_replace, key, value)
                            content_object_to_update_or_replace.save()
                    
                    update_kwargs_for_section_item_save['content_type'] = new_content_type_for_item
                    update_kwargs_for_section_item_save['object_id'] = new_object_id_for_item

                elif existing_type and existing_id:
                    if existing_type != item_type:
                        raise serializers.ValidationError(
                            {"detail": "Тип существующего контента для связи не совпадает с типом элемента."}
                        )
                    model_class = CONTENT_TYPE_MAP[existing_type]['model']
                    new_content_object = get_object_or_404(model_class, pk=existing_id)
                    
                    update_kwargs_for_section_item_save['content_type'] = ContentType.objects.get_for_model(model_class)
                    update_kwargs_for_section_item_save['object_id'] = new_content_object.pk

                serializer.validated_data.pop('validated_material_data', None)
                
                serializer.save(**update_kwargs_for_section_item_save)

        except Exception as e:
            # import traceback; traceback.print_exc();
            raise serializers.ValidationError({"detail": f"Не удалось обновить элемент раздела: {e}"})

    @action(detail=False, methods=['post'], url_path='reorder', permission_classes=[IsAuthenticated, IsCourseStaffOrAdmin])
    def reorder_items(self, request, course_pk=None, lesson_pk=None, section_pk=None):
        section = self._get_section_for_write_operations()

        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Ожидается список объектов с 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)

        updates_map = {}
        new_orders_set = set()
        item_ids_from_payload = []

        for item_payload in data:
            if not isinstance(item_payload, dict) or 'id' not in item_payload or 'order' not in item_payload:
                return Response({"detail": "Каждый элемент должен быть словарем с 'id' и 'order'."}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                item_id = int(item_payload['id'])
                new_order = int(item_payload['order'])
            except (ValueError, TypeError):
                 return Response({"detail": "ID и order должны быть целыми числами."}, status=status.HTTP_400_BAD_REQUEST)

            if new_order < 0:
                return Response({"detail": "Порядок (order) не может быть отрицательным."}, status=status.HTTP_400_BAD_REQUEST)
            if new_order in new_orders_set:
                return Response({"detail": f"Порядок {new_order} указан более одного раза в запросе."}, status=status.HTTP_400_BAD_REQUEST)
            
            new_orders_set.add(new_order)
            item_ids_from_payload.append(item_id)
            updates_map[item_id] = new_order
        
        items_to_update_qs = SectionItem.objects.filter(section=section, id__in=item_ids_from_payload)
        
        if items_to_update_qs.count() != len(set(item_ids_from_payload)):
            return Response(
                {"detail": "Обнаружены дублирующиеся ID элементов в запросе или не все элементы найдены."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        found_ids = set(items_to_update_qs.values_list('id', flat=True))
        if len(found_ids) != len(item_ids_from_payload):
            missing_ids = [sid for sid in item_ids_from_payload if sid not in found_ids]
            return Response(
                {"detail": "Один или несколько указанных элементов не найдены или не принадлежат этому разделу.",
                 "missing_item_ids": missing_ids}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        conflicting_items_qs = SectionItem.objects.filter(section=section, order__in=new_orders_set)\
                                                  .exclude(id__in=item_ids_from_payload)
        if conflicting_items_qs.exists():
            conflict_details = {ci.id: ci.order for ci in conflicting_items_qs}
            return Response(
                {"detail": "Некоторые из новых порядков уже заняты другими элементами этого раздела.",
                 "conflicts_with_other_items": conflict_details},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                max_existing_order_obj = SectionItem.objects.filter(section=section).aggregate(max_val=Max('order'))
                max_existing_order = max_existing_order_obj['max_val'] if max_existing_order_obj['max_val'] is not None else -1
                
                max_payload_order = 0
                if new_orders_set:
                    max_payload_order = max(new_orders_set)
                
                temp_order_start = max(max_existing_order, max_payload_order) + len(item_ids_from_payload) + 100
                items_being_updated_instances = list(items_to_update_qs) 

                for i, item_instance in enumerate(items_being_updated_instances):
                    item_instance.order = temp_order_start + i
                    item_instance.save(update_fields=['order'])
                
                for item_id_to_update, target_order in updates_map.items():
                    item_to_set_final_order = next((it for it in items_being_updated_instances if it.id == item_id_to_update), None)
                    if item_to_set_final_order:
                        item_to_set_final_order.order = target_order
                        item_to_set_final_order.save(update_fields=['order'])
                    else:
                        raise ValueError(f"Логическая ошибка: не найден инстанс для item_id {item_id_to_update}.")
            
            updated_section_items_qs = SectionItem.objects.filter(section=section).order_by('order')
            response_serializer = self.get_serializer(updated_section_items_qs, many=True, context={'request': request})
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except IntegrityError as e:
            return Response({"detail": f"Ошибка целостности базы данных при обновлении порядка: {e}."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"detail": f"Произошла непредвиденная ошибка: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)