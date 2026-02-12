from django.shortcuts import get_object_or_404
from django.db.models import Exists, OuterRef
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
from django.conf import settings
from django.http import HttpResponse, Http404
import grpc
from rest_framework import viewsets, status, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework import serializers

from .models import DictionarySection, DictionaryEntry, UserLearnedEntry, KanjiCharacter
from .serializers import (
    DictionarySectionSerializer, DictionaryEntrySerializer, UserLearnedEntrySerializer,
    get_user_show_learned_setting
)
from .permissions import (
    IsCourseStaffOrAdminForDict, CanViewDictionaryContent, CanMarkLearned
)

from course_service.models import Course
from lesson_service.models import Lesson

from django.utils import timezone
from kei_backend.utils import send_to_kafka

from .kanji_recognition_service import KanjiRecognitionService
from .kanji_serializers import (
    KanjiRecognizeRequestSerializer, KanjiRecognizeResponseSerializer,
    KanjiCharacterSerializer
)

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class DictionarySectionViewSet(viewsets.ModelViewSet):
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
        else:
            user = self.request.user
            
            if user.is_staff or user.is_superuser or (hasattr(user, 'role') and user.role == 'admin'):
                pass 
            else:
                accessible_courses = []
                
                enrolled_courses = Course.objects.filter(
                    enrollments__student=user,
                    enrollments__status='active'
                )
                accessible_courses.extend(enrolled_courses)
                
                teacher_courses = Course.objects.filter(teachers__teacher=user)
                assistant_courses = Course.objects.filter(assistants__assistant=user)
                accessible_courses.extend(teacher_courses)
                accessible_courses.extend(assistant_courses)
                
                public_courses = Course.objects.filter(status__in=['free', 'published'])
                accessible_courses.extend(public_courses)
                
                accessible_course_ids = list(set(course.id for course in accessible_courses))
                
                if accessible_course_ids:
                    qs = qs.filter(course_id__in=accessible_course_ids)
                else:
                    qs = qs.none()

        return qs

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsCourseStaffOrAdminForDict()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        course_pk = self.kwargs.get('course_pk')
        if not course_pk:
            raise serializers.ValidationError({"course_pk": "Для создания раздела обязательно указывать курс."})
        course = get_object_or_404(Course, pk=course_pk)
        serializer.save(created_by=self.request.user, course=course)


class DictionaryEntryViewSet(viewsets.ModelViewSet):
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

        queryset = DictionaryEntry.objects.filter(section=section).select_related('lesson')

        if user.is_authenticated:
             queryset = queryset.annotate(
                 user_has_learned=Exists(
                     UserLearnedEntry.objects.filter(
                         user=user,
                         entry=OuterRef('pk')
                     )
                 )
             )
             if self.action not in ['mark_learned', 'unmark_learned']:
                 include_learned = self.request.query_params.get('include_learned', '').lower()
                 if include_learned in ['true', '1', 'yes']:
                     pass  
                 elif include_learned in ['false', '0', 'no']:
                     queryset = queryset.filter(user_has_learned=False)
                 else:
                     show_learned = get_user_show_learned_setting(user)
                     if not show_learned:
                         queryset = queryset.filter(user_has_learned=False)

        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsCourseStaffOrAdminForDict()]
        if self.action in ['mark_learned', 'unmark_learned']:
            return [IsAuthenticated(), CanMarkLearned()]
        return [IsAuthenticated()]

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
        entry = self.get_object() 
        user = request.user
        learned_entry, created = UserLearnedEntry.objects.get_or_create(user=user, entry=entry)

        serializer = UserLearnedEntrySerializer(learned_entry)
        if created:
            send_to_kafka('progress_events', {
                'type': 'term_learned',
                'user_id': user.id,
                'entry_id': entry.id,
                'term': entry.term,
                'section_id': entry.section_id,
                'course_id': entry.section.course_id,
                'timestamp': timezone.now().isoformat()
            })
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, CanMarkLearned])
    def unmark_learned(self, request, section_pk=None, pk=None):
        entry = self.get_object()
        user = request.user
        deleted_count, _ = UserLearnedEntry.objects.filter(user=user, entry=entry).delete()

        if deleted_count > 0:
            return Response({"status": "изучение отменено"}, status=status.HTTP_200_OK)
        else:
            return Response({"status": "запись не была отмечена как изученная"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def meta(self, request, section_pk=None):
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


class KanjiRecognitionViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def recognize(self, request):
        serializer = KanjiRecognizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        strokes = serializer.validated_data['strokes']
        top_n = serializer.validated_data.get('top_n', 5)

        service = KanjiRecognitionService()
        try:
            results = service.recognize(strokes=strokes, top_n=top_n)
        except grpc.RpcError as e:
            return Response(
                {
                    'detail': f'gRPC error: {e.code().name}',
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception as e:
            return Response(
                {
                    'detail': f'Failed to recognize kanji: {e}',
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_data = {'results': results}
        out = KanjiRecognizeResponseSerializer(data=response_data)
        out.is_valid(raise_exception=True)
        return Response(out.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='structure/(?P<char>.+)')
    def structure(self, request, char=None):
        if not char:
            return Response({"detail": "Character is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            obj = KanjiCharacter.objects.get(character=char)
        except KanjiCharacter.DoesNotExist:
            return Response({"detail": f"Kanji structure for '{char}' not found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = KanjiCharacterSerializer(obj)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """
        Serve Kanji SVG file from backend storage (local or S3).
        PK is the hex code of the kanji (e.g., '0f9b4').
        """
        kanji_hex = pk.lower()
        if not kanji_hex.isalnum() or len(kanji_hex) > 6:
            return Response(
                {'detail': 'Invalid kanji code format.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        file_path = f"kanji/{kanji_hex}.svg"
        
        try:
            content = None
            
            if settings.DEBUG:
                absolute_path = finders.find(file_path)
                if not absolute_path:
                    if staticfiles_storage.exists(file_path):
                        with staticfiles_storage.open(file_path) as f:
                            content = f.read()
                    else:
                        raise Http404("Kanji SVG not found.")
                else:
                    with open(absolute_path, 'rb') as f:
                        content = f.read()
            else:
                if not staticfiles_storage.exists(file_path):
                    raise Http404("Kanji SVG not found.")

                with staticfiles_storage.open(file_path) as f:
                    content = f.read()
                
            return HttpResponse(content, content_type="image/svg+xml")
            
        except Exception as e:
            if isinstance(e, Http404):
                raise e
            if isinstance(e, FileNotFoundError):
                 raise Http404("Kanji SVG not found.")
            
            return Response(
                {'detail': f'Error retrieving kanji file: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PrimaryLessonEntriesViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = DictionaryEntrySerializer
    permission_classes = [IsAuthenticated]
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

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def meta(self, request, course_pk=None, lesson_pk=None):
        lesson_pk = self.kwargs.get('lesson_pk')
        user = request.user

        if not lesson_pk:
            return Response({"error": "lesson_pk is required"}, status=status.HTTP_400_BAD_REQUEST)

        lesson = get_object_or_404(
            Lesson.objects.select_related('course'),
            pk=lesson_pk
        )

        if not CanViewDictionaryContent().has_object_permission(self.request, self, lesson.course):
            self.permission_denied(self.request, message="Нет доступа к словарю этого урока.")

        try:
            primary_section = DictionarySection.objects.get(course=lesson.course, is_primary=True)
        except DictionarySection.DoesNotExist:
            return Response({
                "total_count": 0,
                "learned_count": 0,
                "unlearned_count": 0,
                "course_id": lesson.course_id,
                "lesson_id": lesson.id,
                "lesson_title": lesson.title,
                "section_id": None,
                "section_title": None,
            })
        except DictionarySection.MultipleObjectsReturned:
            primary_section = DictionarySection.objects.filter(course=lesson.course, is_primary=True).first()
            if not primary_section:
                return Response({
                    "total_count": 0,
                    "learned_count": 0,
                    "unlearned_count": 0,
                    "course_id": lesson.course_id,
                    "lesson_id": lesson.id,
                    "lesson_title": lesson.title,
                    "section_id": None,
                    "section_title": None,
                })

        base_queryset = DictionaryEntry.objects.filter(section=primary_section, lesson=lesson)
        total_count = base_queryset.count()

        learned_count = 0
        unlearned_count = total_count
        if user.is_authenticated:
            learned_entries = UserLearnedEntry.objects.filter(
                user=user,
                entry__section=primary_section,
                entry__lesson=lesson
            ).values_list('entry_id', flat=True)
            learned_count = len(learned_entries)
            unlearned_count = total_count - learned_count

        return Response({
            "total_count": total_count,
            "learned_count": learned_count,
            "unlearned_count": unlearned_count,
            "course_id": lesson.course_id,
            "lesson_id": lesson.id,
            "lesson_title": lesson.title,
            "section_id": primary_section.id,
            "section_title": primary_section.title,
        })

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context