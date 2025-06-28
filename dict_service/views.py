# dict_service/views.py
from django.shortcuts import get_object_or_404
from django.db.models import Exists, OuterRef
from rest_framework import viewsets, status, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import serializers

from .models import DictionarySection, DictionaryEntry, UserLearnedEntry
from .serializers import (
    DictionarySectionSerializer, DictionaryEntrySerializer, UserLearnedEntrySerializer,
    get_user_show_learned_setting
)
from .permissions import (
    IsCourseStaffOrAdminForDict, CanViewDictionaryContent, CanMarkLearned
)

from course_service.models import Course
from lesson_service.models import Lesson

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20 # Количество элементов на странице
    page_size_query_param = 'page_size'
    max_page_size = 100

class DictionarySectionViewSet(viewsets.ModelViewSet):
    """
    Теперь работает и по /dictionary_sections/ (корень) и по
    /courses/{course_pk}/dictionary_sections/ (вложенный).
    """
    serializer_class = DictionarySectionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        course_pk = self.kwargs.get('course_pk')

        qs = DictionarySection.objects.select_related('course')

        if course_pk:
            course = get_object_or_404(Course, pk=course_pk)
            if not CanViewDictionaryContent().has_object_permission(self.request, self, course):
                self.permission_denied(self.request, message="Нет доступа к словарю этого курса.")
            qs = qs.filter(course=course)

        return qs

    def get_permissions(self):
        # для write-действий — только персонал курса
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsCourseStaffOrAdminForDict()]
        # для чтения (list, retrieve) — проверяем право видеть контент
        return [IsAuthenticated(), CanViewDictionaryContent()]

    def perform_create(self, serializer):
        # создаём только если передан course_pk
        course_pk = self.kwargs.get('course_pk')
        if not course_pk:
            raise serializers.ValidationError({"course_pk": "Для создания раздела обязательно указывать курс."})
        course = get_object_or_404(Course, pk=course_pk)
        serializer.save(created_by=self.request.user, course=course)


class DictionaryEntryViewSet(viewsets.ModelViewSet):
    """Управление записями словаря в рамках раздела."""
    serializer_class = DictionaryEntrySerializer
    permission_classes = [IsAuthenticated] 
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['term', 'reading', 'translation'] 
    ordering_fields = ['term', 'reading', 'created_at']
    ordering = ['term'] 

    def get_queryset(self):
        section_pk = self.kwargs.get('section_pk')
        user = self.request.user

        if not section_pk:
            return DictionaryEntry.objects.none()

        section = get_object_or_404(
            DictionarySection.objects.select_related('course'),
            pk=section_pk
        )
        if not CanViewDictionaryContent().has_object_permission(self.request, self, section):
            self.permission_denied(self.request, message="Нет доступа к этому разделу словаря.")

        queryset = DictionaryEntry.objects.filter(section=section).select_related('lesson') # Добавляем lesson

        if user.is_authenticated:
             queryset = queryset.annotate(
                 user_has_learned=Exists(
                     UserLearnedEntry.objects.filter(
                         user=user,
                         entry=OuterRef('pk')
                     )
                 )
             )
             # Проверяем параметр запроса include_learned
             include_learned = self.request.query_params.get('include_learned', '').lower()
             if include_learned in ['true', '1', 'yes']:
                 # Показываем все записи (включая изученные)
                 pass  
             elif include_learned in ['false', '0', 'no']:
                 # Скрываем изученные записи
                 queryset = queryset.filter(user_has_learned=False)
             else:
                 # Используем настройку пользователя по умолчанию
                 show_learned = get_user_show_learned_setting(user)
                 if not show_learned:
                     queryset = queryset.filter(user_has_learned=False)

        return queryset

    def get_permissions(self):
        """Чтение для тех, кто видит раздел, Запись - для персонала курса, Отметка - для тех, кто видит."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsCourseStaffOrAdminForDict()]
        if self.action in ['mark_learned', 'unmark_learned']:
            return [IsAuthenticated(), CanMarkLearned()]
        # list, retrieve
        return [IsAuthenticated(), CanViewDictionaryContent()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        section_pk = self.kwargs['section_pk']
        section = get_object_or_404(DictionarySection, pk=section_pk)
        lesson_id = self.request.data.get('lesson')
        lesson = None
        if lesson_id:
             try:
                 lesson = Lesson.objects.get(pk=lesson_id, course=section.course)
             except Lesson.DoesNotExist:
                  raise serializers.ValidationError({"lesson": "Указанный урок не найден или не принадлежит курсу этого раздела."})

        serializer.save(created_by=self.request.user, section=section, lesson=lesson)

    def perform_update(self, serializer):
         lesson_id = self.request.data.get('lesson')
         lesson = None
         if lesson_id is not None:
             section = serializer.instance.section
             if lesson_id:
                 try:
                     lesson = Lesson.objects.get(pk=lesson_id, course=section.course)
                 except Lesson.DoesNotExist:
                     raise serializers.ValidationError({"lesson": "Указанный урок не найден или не принадлежит курсу этого раздела."})
             serializer.save(lesson=lesson) 
         else:
             serializer.save() 


    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanMarkLearned])
    def mark_learned(self, request, section_pk=None, pk=None):
        """Отметить запись как изученную."""
        entry = self.get_object() 
        user = request.user
        learned_entry, created = UserLearnedEntry.objects.get_or_create(user=user, entry=entry)

        serializer = UserLearnedEntrySerializer(learned_entry)
        if created:
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanMarkLearned])
    def unmark_learned(self, request, section_pk=None, pk=None):
        """Снять отметку 'изучено'."""
        entry = self.get_object()
        user = request.user
        deleted_count, _ = UserLearnedEntry.objects.filter(user=user, entry=entry).delete()

        if deleted_count > 0:
            return Response({"status": "изучение отменено"}, status=status.HTTP_200_OK)
        else:
            return Response({"status": "запись не была отмечена как изученная"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, CanViewDictionaryContent])
    def meta(self, request, section_pk=None):
        """Получить метаданные о записях словаря (общее количество, количество изученных и т.д.)."""
        section_pk = self.kwargs.get('section_pk')
        user = request.user

        if not section_pk:
            return Response({"error": "section_pk is required"}, status=status.HTTP_400_BAD_REQUEST)

        section = get_object_or_404(
            DictionarySection.objects.select_related('course'),
            pk=section_pk
        )
        
        if not CanViewDictionaryContent().has_object_permission(self.request, self, section):
            self.permission_denied(self.request, message="Нет доступа к этому разделу словаря.")

        # Получаем queryset с теми же фильтрами что и в get_queryset
        base_queryset = DictionaryEntry.objects.filter(section=section)
        
        total_count = base_queryset.count()
        learned_count = 0
        unlearned_count = total_count
        
        if user.is_authenticated:
            learned_entries = UserLearnedEntry.objects.filter(
                user=user,
                entry__section=section
            ).values_list('entry_id', flat=True)
            
            learned_count = len(learned_entries)
            unlearned_count = total_count - learned_count

        return Response({
            "total_count": total_count,
            "learned_count": learned_count,
            "unlearned_count": unlearned_count,
            "section_id": section.id,
            "section_title": section.title
        })


class PrimaryLessonEntriesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Предоставляет список словарных записей из ОСНОВНОГО раздела курса
    для КОНКРЕТНОГО урока. Используется для "книжечки" на уроке.
    """
    serializer_class = DictionaryEntrySerializer
    permission_classes = [IsAuthenticated] # Доступ проверяется через урок
    pagination_class = StandardResultsSetPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter] 
    search_fields = ['term', 'reading', 'translation']
    ordering_fields = ['term', 'reading', 'created_at']
    ordering = ['term']

    def get_queryset(self):
        lesson_pk = self.kwargs.get('lesson_pk')
        user = self.request.user

        if not lesson_pk:
            return DictionaryEntry.objects.none()

        lesson = get_object_or_404(
            Lesson.objects.select_related('course'), 
            pk=lesson_pk
        )

        if not CanViewDictionaryContent().has_object_permission(self.request, self, lesson.course):
             self.permission_denied(self.request, message="Нет доступа к словарю этого урока.")

        try:
            primary_section = DictionarySection.objects.get(course=lesson.course, is_primary=True)
        except DictionarySection.DoesNotExist:
             return DictionaryEntry.objects.none()
        except DictionarySection.MultipleObjectsReturned:
             primary_section = DictionarySection.objects.filter(course=lesson.course, is_primary=True).first()
             if not primary_section: return DictionaryEntry.objects.none()


        queryset = DictionaryEntry.objects.filter(
            section=primary_section,
            lesson=lesson
        )

        if user.is_authenticated:
             queryset = queryset.annotate(
                 user_has_learned=Exists(
                     UserLearnedEntry.objects.filter(
                         user=user,
                         entry=OuterRef('pk')
                     )
                 )
             )
             show_learned = get_user_show_learned_setting(user)
             if not show_learned:
                 queryset = queryset.filter(user_has_learned=False)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context