from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction

from .models import Exam, ExamSection, ExamSectionItem, ExamAttempt, ExamAnswer
from .serializers import (
    ExamListSerializer, ExamDetailSerializer, ExamCreateSerializer,
    ExamAttemptSerializer, ExamSectionSubmitSerializer,
    ExamSectionSerializer, ExamSectionItemSerializer,
    ExamSectionWriteSerializer, ExamSectionItemWriteSerializer,
    GradeAnswerSerializer,
)
from course_service.models import CourseTeacher, CourseAssistant
from progress_service.models import CourseProgress
from material_service.models import (
    Test, MCQOption, WordOrderSentence, MatchingPair,
)


def _check_exam_teacher_permission(user, exam):
    if user.role == 'admin':
        return True
    course = exam.course
    is_teacher = CourseTeacher.objects.filter(course=course, teacher=user).exists()
    is_assistant = CourseAssistant.objects.filter(course=course, assistant=user).exists()
    return is_teacher or is_assistant


class ExamSectionViewSet(viewsets.ModelViewSet):
    """CRUD для секций экзамена."""
    permission_classes = [IsAuthenticated]
    serializer_class = ExamSectionWriteSerializer

    def get_exam(self):
        exam = Exam.objects.get(pk=self.kwargs['exam_id'])
        if not _check_exam_teacher_permission(self.request.user, exam):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Нет прав для управления секциями этого экзамена.")
        return exam

    def get_queryset(self):
        return ExamSection.objects.filter(exam_id=self.kwargs['exam_id']).order_by('order')

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ExamSectionSerializer
        return ExamSectionWriteSerializer

    def perform_create(self, serializer):
        exam = self.get_exam()
        order = serializer.validated_data.get('order')
        if order is None:
            max_order = ExamSection.objects.filter(exam=exam).count()
            serializer.save(exam=exam, order=max_order)
        else:
            serializer.save(exam=exam)

    def perform_update(self, serializer):
        self.get_exam()
        serializer.save()

    def perform_destroy(self, instance):
        self.get_exam()
        instance.delete()


class ExamSectionItemViewSet(viewsets.ModelViewSet):
    """CRUD для элементов секции экзамена (тестов внутри секции)."""
    permission_classes = [IsAuthenticated]
    serializer_class = ExamSectionItemWriteSerializer

    def get_section(self):
        section = ExamSection.objects.select_related('exam').get(
            pk=self.kwargs['section_id'],
            exam_id=self.kwargs['exam_id']
        )
        if not _check_exam_teacher_permission(self.request.user, section.exam):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Нет прав.")
        return section

    def get_queryset(self):
        return ExamSectionItem.objects.filter(
            section_id=self.kwargs['section_id'],
            section__exam_id=self.kwargs['exam_id']
        ).select_related('test').order_by('order')

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return ExamSectionItemSerializer
        return ExamSectionItemWriteSerializer

    def perform_create(self, serializer):
        section = self.get_section()
        order = serializer.validated_data.get('order')
        if order is None:
            max_order = ExamSectionItem.objects.filter(section=section).count()
            serializer.save(section=section, order=max_order)
        else:
            serializer.save(section=section)

    def perform_update(self, serializer):
        self.get_section()
        serializer.save()

    def perform_destroy(self, instance):
        self.get_section()
        instance.delete()



class ExamViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Exam.objects.select_related('course', 'created_by').prefetch_related(
            'sections__items__test'
        )
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)

        if user.role not in ['admin', 'teacher', 'assistant']:
            qs = qs.filter(is_published=True)
        return qs

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ExamCreateSerializer
        if self.action == 'list':
            return ExamListSerializer
        return ExamDetailSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def check_teacher_permission(self, request, exam=None):
        user = request.user
        if user.role == 'admin':
            return True
        if exam:
            course = exam.course
        else:
            course_id = request.data.get('course')
            if not course_id:
                return False
            from course_service.models import Course
            try:
                course = Course.objects.get(pk=course_id)
            except Course.DoesNotExist:
                return False
        is_teacher = CourseTeacher.objects.filter(course=course, teacher=user).exists()
        is_assistant = CourseAssistant.objects.filter(course=course, assistant=user).exists()
        return is_teacher or is_assistant

    def create(self, request, *args, **kwargs):
        if not self.check_teacher_permission(request):
            return Response(
                {"detail": "У вас нет прав для создания экзамена к этому курсу."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        exam = self.get_object()
        if not self.check_teacher_permission(request, exam):
            return Response(
                {"detail": "У вас нет прав для редактирования этого экзамена."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        exam = self.get_object()
        if not self.check_teacher_permission(request, exam):
            return Response(
                {"detail": "У вас нет прав для удаления этого экзамена."},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)


    @action(detail=True, methods=['get'])
    def check_eligibility(self, request, pk=None):
        """Проверить, может ли студент начать экзамен (курс завершён?)."""
        exam = self.get_object()
        user = request.user

        try:
            progress = CourseProgress.objects.get(user=user, course=exam.course)
            is_eligible = float(progress.completion_percentage) >= 100
        except CourseProgress.DoesNotExist:
            is_eligible = False

        existing = ExamAttempt.objects.filter(exam=exam, student=user).first()

        return Response({
            "is_eligible": is_eligible,
            "has_attempt": existing is not None,
            "attempt_status": existing.status if existing else None,
            "attempt_id": existing.id if existing else None,
        })

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Начать экзамен. Создаёт ExamAttempt."""
        exam = self.get_object()
        user = request.user

        if not exam.is_published:
            return Response(
                {"detail": "Экзамен не опубликован."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            progress = CourseProgress.objects.get(user=user, course=exam.course)
            if float(progress.completion_percentage) < 100:
                return Response(
                    {"detail": "Необходимо завершить курс перед экзаменом."},
                    status=status.HTTP_403_FORBIDDEN
                )
        except CourseProgress.DoesNotExist:
            return Response(
                {"detail": "Необходимо пройти курс перед экзаменом."},
                status=status.HTTP_403_FORBIDDEN
            )

        existing = ExamAttempt.objects.filter(exam=exam, student=user).first()
        if existing:
            if existing.status == 'in_progress':
                serializer = ExamAttemptSerializer(existing, context={'request': request})
                exam_data = ExamDetailSerializer(exam, context={'request': request}).data
                return Response({
                    "attempt": serializer.data,
                    "exam": exam_data,
                    "resumed": True
                })
            return Response(
                {"detail": "Вы уже прошли этот экзамен."},
                status=status.HTTP_400_BAD_REQUEST
            )

        attempt = ExamAttempt.objects.create(
            exam=exam,
            student=user,
            status='in_progress',
            current_section_order=0,
            started_at=timezone.now()
        )

        serializer = ExamAttemptSerializer(attempt, context={'request': request})
        exam_data = ExamDetailSerializer(exam, context={'request': request}).data

        return Response({
            "attempt": serializer.data,
            "exam": exam_data,
            "resumed": False
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='submit-section')
    def submit_section(self, request, pk=None):
        """Отправить ответы за текущую секцию. Переход на следующую."""
        exam = self.get_object()
        user = request.user

        try:
            attempt = ExamAttempt.objects.get(exam=exam, student=user, status='in_progress')
        except ExamAttempt.DoesNotExist:
            return Response(
                {"detail": "Активная сессия экзамена не найдена."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if attempt.is_expired:
            attempt.status = 'timed_out'
            attempt.finished_at = timezone.now()
            attempt.save()
            self._calculate_total_score(attempt)
            return Response(
                {"detail": "Время экзамена истекло.", "status": "timed_out"},
                status=status.HTTP_400_BAD_REQUEST
            )

        input_serializer = ExamSectionSubmitSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        section_order = input_serializer.validated_data['section_order']
        answers_data = input_serializer.validated_data['answers']

        if section_order != attempt.current_section_order:
            return Response(
                {"detail": f"Ожидается секция #{attempt.current_section_order}, а получена #{section_order}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            for ans in answers_data:
                item_id = ans['exam_section_item_id']
                answer_data = ans['answer_data']

                try:
                    item = ExamSectionItem.objects.select_related('test', 'section').get(
                        pk=item_id,
                        section__exam=exam,
                        section__order=section_order
                    )
                except ExamSectionItem.DoesNotExist:
                    continue

                score, is_correct = self._auto_grade(item.test, answer_data)

                submitted_file = request.FILES.get(f'file_{item_id}')

                ExamAnswer.objects.update_or_create(
                    attempt=attempt,
                    exam_section_item=item,
                    defaults={
                        'answer_data': answer_data,
                        'submitted_file': submitted_file,
                        'score': score,
                        'is_correct': is_correct,
                    }
                )

            total_sections = exam.sections.count()
            next_order = section_order + 1
            
            if next_order >= total_sections:
                attempt.current_section_order = next_order
                attempt.status = 'completed'
                attempt.finished_at = timezone.now()
                attempt.save()
                self._calculate_total_score(attempt)
            else:
                attempt.current_section_order = next_order
                attempt.save()

        serializer = ExamAttemptSerializer(attempt, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        """Досрочно завершить экзамен."""
        exam = self.get_object()
        user = request.user

        try:
            attempt = ExamAttempt.objects.get(exam=exam, student=user, status='in_progress')
        except ExamAttempt.DoesNotExist:
            return Response(
                {"detail": "Активная сессия экзамена не найдена."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if attempt.is_expired:
            attempt.status = 'timed_out'
        else:
            attempt.status = 'completed'
        attempt.finished_at = timezone.now()
        attempt.save()
        self._calculate_total_score(attempt)

        serializer = ExamAttemptSerializer(attempt, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def result(self, request, pk=None):
        """Получить результат экзамена."""
        exam = self.get_object()
        user = request.user

        student_id = request.query_params.get('student_id')
        if student_id and user.role in ['admin', 'teacher', 'assistant']:
            target_user_id = student_id
        else:
            target_user_id = user.id

        try:
            attempt = ExamAttempt.objects.get(exam=exam, student_id=target_user_id)
        except ExamAttempt.DoesNotExist:
            return Response(
                {"detail": "Попытка экзамена не найдена."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ExamAttemptSerializer(attempt, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def all_attempts(self, request, pk=None):
        """Get all attempts for this exam (for teachers)."""
        exam = self.get_object()
        if not self.check_teacher_permission(request, exam):
            return Response(
                {"detail": "У вас нет прав для просмотра результатов."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        attempts = ExamAttempt.objects.filter(exam=exam).select_related('student')
        serializer = ExamAttemptSerializer(attempts, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='grade-answer/(?P<answer_id>[^/.]+)')
    def grade_answer(self, request, answer_id=None):
        """Manually grade an answer (for teachers)."""
        try:
            answer = ExamAnswer.objects.select_related('attempt__exam').get(pk=answer_id)
        except ExamAnswer.DoesNotExist:
            return Response({"detail": "Ответ не найден."}, status=status.HTTP_404_NOT_FOUND)

        if not self.check_teacher_permission(request, answer.attempt.exam):
             return Response(
                {"detail": "У вас нет прав для оценивания этого ответа."},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = GradeAnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        answer.score = serializer.validated_data['score']
        answer.is_correct = serializer.validated_data.get('is_correct', True)
        answer.save()
        
        self._calculate_total_score(answer.attempt)
        
        return Response({
            "detail": "Оценка сохранена.", 
            "new_total_score": float(answer.attempt.total_score)
        })


    def _auto_grade(self, test, answer_data):
        """Auto-grade auto-checkable test types. Returns (score, is_correct)."""
        test_type = test.test_type

        if test_type in ['mcq-single', 'mcq-multi']:
            selected_ids = set(answer_data.get('selected_option_ids', []))
            correct_ids = set(
                MCQOption.objects.filter(test=test, is_correct=True).values_list('id', flat=True)
            )
            if test_type == 'mcq-single':
                if len(selected_ids) == 1 and selected_ids == correct_ids:
                    return 1.0, True
                return 0.0, False
            else:
                total = len(correct_ids)
                if total == 0:
                    return 1.0, True
                correct = len(selected_ids & correct_ids)
                wrong = len(selected_ids - correct_ids)
                if wrong > 0:
                    return 0.0, False
                if correct == total:
                    return 1.0, True
                return round(correct / total, 2), False

        elif test_type == 'word-order':
            submitted = answer_data.get('submitted_order_words', [])
            wos = getattr(test, 'word_order_sentence_details', None)
            if wos and submitted == wos.correct_ordered_texts:
                return 1.0, True
            return 0.0, False

        elif test_type == 'drag-and-drop':
            submitted = answer_data.get('answers', [])
            slots = {s.id: s for s in test.drag_drop_slots.all()}
            total = len(slots)
            correct = 0
            for ans in submitted:
                slot_id = ans.get('slot_id')
                text = ans.get('dropped_option_text')
                if slot_id in slots and slots[slot_id].correct_answer_text == text:
                    correct += 1
            if total > 0:
                score = correct / total
                return round(score, 2), score == 1.0
            return 1.0, True

        return None, None

    def _calculate_total_score(self, attempt):
        """Calculate combined score from all answers."""
        answers = attempt.answers.all()
        total = 0.0
        max_score = answers.count()
        for ans in answers:
            if ans.score is not None:
                total += float(ans.score)
        attempt.total_score = round(total, 2)
        attempt.max_possible_score = max_score
        attempt.save(update_fields=['total_score', 'max_possible_score'])
