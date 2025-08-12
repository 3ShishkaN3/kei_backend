import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from progress_service.models import UserProgress, CourseProgress
from course_service.models import Course, CourseEnrollment
from kafka import KafkaConsumer

User = get_user_model()


class Command(BaseCommand):
    help = "Прослушивание событий курсов из Kafka и обновление данных прогресса"

    def handle(self, *args, **options):
        consumer = KafkaConsumer(
            'course_events', 
            bootstrap_servers=['localhost:9092'],
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        self.stdout.write(self.style.SUCCESS("Начало прослушивания топика 'course_events'..."))
        
        for message in consumer:
            data = message.value
            event_type = data.get('type')
            user_id = data.get('user_id')
            course_id = data.get('course_id')
            
            self.stdout.write(f"Получено событие: {event_type} для пользователя {user_id} и курса {course_id}")
            
            try:
                user = User.objects.get(pk=user_id)
                course = Course.objects.get(pk=course_id)
            except (User.DoesNotExist, Course.DoesNotExist) as e:
                self.stdout.write(f"Пользователь или курс не найден: {e}")
                continue
            
            try:
                with transaction.atomic():
                    if event_type == 'enrollment':
                        self.handle_enrollment(data, user, course)
                    elif event_type == 'leave_course':
                        self.handle_leave_course(data, user, course)
                    elif event_type == 'course_completed':
                        self.handle_course_completed(data, user, course)
                    else:
                        self.stdout.write(f"Неизвестный тип события: {event_type}")
                        
            except Exception as e:
                self.stdout.write(f"Ошибка обработки события {event_type}: {e}")

    def handle_enrollment(self, data, user, course):
        """Обработка записи на курс"""
        # Создаем или обновляем прогресс по курсу
        course_progress, created = CourseProgress.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'total_lessons': course.lessons.count(),
                'total_sections': sum(lesson.sections.count() for lesson in course.lessons.all()),
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            course_progress.last_activity = timezone.now()
            course_progress.save()
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)
        
        self.stdout.write(f"Прогресс по курсу {course.title} создан для пользователя {user.username}")

    def handle_leave_course(self, data, user, course):
        """Обработка отчисления с курса"""
        # Удаляем прогресс по курсу
        try:
            course_progress = CourseProgress.objects.get(user=user, course=course)
            course_progress.delete()
            self.stdout.write(f"Прогресс по курсу {course.title} удален для пользователя {user.username}")
        except CourseProgress.DoesNotExist:
            self.stdout.write(f"Прогресс по курсу {course.title} не найден для пользователя {user.username}")
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)

    def handle_course_completed(self, data, user, course):
        """Обработка завершения курса"""
        try:
            course_progress = CourseProgress.objects.get(user=user, course=course)
            course_progress.completion_percentage = 100.00
            course_progress.completed_at = timezone.now()
            course_progress.last_activity = timezone.now()
            course_progress.save()
            
            self.stdout.write(f"Курс {course.title} отмечен как завершенный для пользователя {user.username}")
        except CourseProgress.DoesNotExist:
            self.stdout.write(f"Прогресс по курсу {course.title} не найден для пользователя {user.username}")
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)

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
        
        progress.save()
