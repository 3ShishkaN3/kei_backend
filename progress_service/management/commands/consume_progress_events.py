import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from progress_service.models import (
    UserProgress, CourseProgress, LessonProgress, TestProgress, LearningStats
)
from course_service.models import Course, CourseEnrollment
from lesson_service.models import Lesson, Section
from kafka import KafkaConsumer

User = get_user_model()


class Command(BaseCommand):
    help = "Прослушивание событий прогресса из Kafka и обновление данных прогресса"

    def handle(self, *args, **options):
        consumer = KafkaConsumer(
            'progress_events', 
            bootstrap_servers=['localhost:9092'],
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        self.stdout.write(self.style.SUCCESS("Начало прослушивания топика 'progress_events'..."))
        
        for message in consumer:
            data = message.value
            event_type = data.get('type')
            user_id = data.get('user_id')
            
            self.stdout.write(f"Получено событие: {event_type} для пользователя {user_id}")
            
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                self.stdout.write(f"Пользователь с id {user_id} не найден")
                continue
            
            try:
                with transaction.atomic():
                    if event_type == 'lesson_completed':
                        self.handle_lesson_completed(data, user)
                    elif event_type == 'section_completed':
                        self.handle_section_completed(data, user)
                    elif event_type == 'test_submitted':
                        self.handle_test_submitted(data, user)
                    else:
                        self.stdout.write(f"Неизвестный тип события: {event_type}")
                        
            except Exception as e:
                self.stdout.write(f"Ошибка обработки события {event_type}: {e}")

    def handle_lesson_completed(self, data, user):
        """Обработка завершения урока"""
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        
        try:
            lesson = Lesson.objects.get(pk=lesson_id)
        except Lesson.DoesNotExist:
            self.stdout.write(f"Урок с id {lesson_id} не найден")
            return
        
        # Обновляем или создаем прогресс по уроку
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={
                'total_sections': lesson.sections.count(),
                'completed_sections': lesson.sections.count(),
                'completion_percentage': 100.00,
                'completed_at': timezone.now(),
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            lesson_progress.completed_sections = lesson.sections.count()
            lesson_progress.completion_percentage = 100.00
            lesson_progress.completed_at = timezone.now()
            lesson_progress.last_activity = timezone.now()
            lesson_progress.save()
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)
        
        # Обновляем прогресс по курсу
        self.update_course_progress(user, course_id)
        
        self.stdout.write(f"Прогресс по уроку {lesson_id} обновлен для пользователя {user.username}")

    def handle_section_completed(self, data, user):
        """Обработка завершения раздела"""
        section_id = data.get('section_id')
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        
        try:
            section = Section.objects.get(pk=section_id)
            lesson = section.lesson
        except Section.DoesNotExist:
            self.stdout.write(f"Раздел с id {section_id} не найден")
            return
        
        # Обновляем или создаем прогресс по уроку
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={
                'total_sections': lesson.sections.count(),
                'completed_sections': 1,
                'completion_percentage': (1 / lesson.sections.count()) * 100,
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            # Подсчитываем количество завершенных разделов
            completed_sections = Section.objects.filter(
                lesson=lesson,
                completions__student=user
            ).count()
            
            lesson_progress.completed_sections = completed_sections
            lesson_progress.completion_percentage = (completed_sections / lesson.sections.count()) * 100
            lesson_progress.last_activity = timezone.now()
            
            # Если все разделы завершены, отмечаем урок как завершенный
            if completed_sections == lesson.sections.count():
                lesson_progress.completed_at = timezone.now()
            
            lesson_progress.save()
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)
        
        # Обновляем прогресс по курсу
        self.update_course_progress(user, course_id)
        
        self.stdout.write(f"Прогресс по разделу {section_id} обновлен для пользователя {user.username}")

    def handle_test_submitted(self, data, user):
        """Обработка отправки теста"""
        test_id = data.get('test_id')
        test_title = data.get('test_title')
        test_type = data.get('test_type')
        section_id = data.get('section_id')
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        submission_id = data.get('submission_id')
        status = data.get('status')
        
        # Обновляем или создаем прогресс по тесту
        test_progress, created = TestProgress.objects.get_or_create(
            user=user,
            test_id=test_id,
            defaults={
                'test_title': test_title,
                'test_type': test_type,
                'section_id': section_id,
                'lesson_id': lesson_id,
                'course_id': course_id,
                'attempts_count': 1,
                'first_attempt_at': timezone.now(),
                'last_attempt_at': timezone.now(),
                'status': 'in_progress'
            }
        )
        
        if not created:
            test_progress.attempts_count += 1
            test_progress.last_attempt_at = timezone.now()
            
            # Обновляем статус на основе результата
            if status in ['passed', 'auto_passed']:
                test_progress.status = 'passed'
                test_progress.completed_at = timezone.now()
            elif status in ['failed', 'auto_failed']:
                test_progress.status = 'failed'
            
            test_progress.save()
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)
        
        # Обновляем прогресс по курсу
        self.update_course_progress(user, course_id)
        
        self.stdout.write(f"Прогресс по тесту {test_id} обновлен для пользователя {user.username}")

    def update_user_progress(self, user):
        """Обновление общего прогресса пользователя"""
        progress, created = UserProgress.objects.get_or_create(
            user=user,
            defaults={
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            progress.last_activity = timezone.now()
        
        # Подсчитываем статистику
        progress.total_courses_enrolled = CourseEnrollment.objects.filter(
            student=user, status='active'
        ).count()
        
        progress.total_courses_completed = CourseEnrollment.objects.filter(
            student=user, status='completed'
        ).count()
        
        progress.total_lessons_completed = LessonProgress.objects.filter(
            user=user, completion_percentage=100
        ).count()
        
        progress.total_sections_completed = Section.objects.filter(
            completions__student=user
        ).count()
        
        progress.total_tests_passed = TestProgress.objects.filter(
            user=user, status='passed'
        ).count()
        
        progress.total_tests_failed = TestProgress.objects.filter(
            user=user, status='failed'
        ).count()
        
        progress.save()

    def update_course_progress(self, user, course_id):
        """Обновление прогресса по курсу"""
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return
        
        course_progress, created = CourseProgress.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            course_progress.last_activity = timezone.now()
        
        # Подсчитываем статистику по курсу
        course_progress.total_lessons = course.lessons.count()
        course_progress.completed_lessons = LessonProgress.objects.filter(
            user=user, lesson__course=course, completion_percentage=100
        ).count()
        
        course_progress.total_sections = Section.objects.filter(
            lesson__course=course
        ).count()
        
        course_progress.completed_sections = Section.objects.filter(
            lesson__course=course, completions__student=user
        ).count()
        
        course_progress.total_tests = TestProgress.objects.filter(
            user=user, course_id=course_id
        ).count()
        
        course_progress.passed_tests = TestProgress.objects.filter(
            user=user, course_id=course_id, status='passed'
        ).count()
        
        course_progress.failed_tests = TestProgress.objects.filter(
            user=user, course_id=course_id, status='failed'
        ).count()
        
        # Рассчитываем процент завершения
        total_items = course_progress.total_lessons + course_progress.total_sections + course_progress.total_tests
        completed_items = course_progress.completed_lessons + course_progress.completed_sections + course_progress.passed_tests
        
        if total_items > 0:
            course_progress.completion_percentage = (completed_items / total_items) * 100
        else:
            course_progress.completion_percentage = 0.00
        
        # Если курс завершен, устанавливаем дату завершения
        if course_progress.completion_percentage >= 100 and not course_progress.completed_at:
            course_progress.completed_at = timezone.now()
        
        course_progress.save()
