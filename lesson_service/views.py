from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
from .models import Lesson, Section, SectionCompletion, LessonCompletion
from .serializers import (
    LessonListSerializer, LessonDetailSerializer, SectionSerializer,
    SectionCompletionSerializer, LessonCompletionSerializer
)
from .permissions import LessonPermission, SectionPermission, CanComplete, IsCourseStaffOrAdmin, CanViewLessonOrSectionContent
from kei_backend.utils import send_to_kafka

from course_service.models import Course

class LessonViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, LessonPermission]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title', 'subtitle', 'description']
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
        course_pk = self.kwargs.get('course_pk')
        lesson_pk = self.kwargs.get('lesson_pk')

        if not course_pk or not lesson_pk:
            return Section.objects.none()

        lesson = get_object_or_404(Lesson, pk=lesson_pk, course_id=course_pk)


        if not CanViewLessonOrSectionContent().has_object_permission(self.request, self, lesson):
             self.permission_denied(self.request, message="У вас нет доступа к этому уроку.")

        return Section.objects.filter(lesson=lesson)

    def perform_create(self, serializer):
        course_pk = self.kwargs.get('course_pk')
        lesson_pk = self.kwargs.get('lesson_pk')
        lesson = get_object_or_404(Lesson, pk=lesson_pk, course_id=course_pk)

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