import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from course_service.models import Course, CourseEnrollment
from kafka import KafkaConsumer
from decouple import config

class Command(BaseCommand):
    help = "Прослушивание событий из Kafka от сервисов, связанных с курсами"

    def handle(self, *args, **options):
        
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=lambda v: [s.strip() for s in v.split(',')])
        
        consumer = KafkaConsumer(
            'course_events', 
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            session_timeout_ms=30000,
            heartbeat_interval_ms=3000
        )
        self.stdout.write(self.style.SUCCESS(f"Начало прослушивания топика 'course_events' с серверами: {bootstrap_servers}..."))
        for message in consumer:
            data = message.value
            event_type = data.get('type')
            course_id = data.get('course_id')
            user_id = data.get('user_id')
            self.stdout.write(f"Получено событие: {event_type} для пользователя {user_id} и курса {course_id}")

            try:
                course = Course.objects.get(pk=course_id)
            except Course.DoesNotExist:
                self.stdout.write(f"Курс с id {course_id} не найден")
                continue

            if event_type == 'user_added':
                enrollment, created = CourseEnrollment.objects.get_or_create(
                    course=course,
                    student_id=user_id,
                    defaults={'status': 'active'}
                )
                if not created and enrollment.status != 'active':
                    enrollment.status = 'active'
                    enrollment.save()
                self.stdout.write(f"Пользователь {user_id} записан на курс {course_id}")

            elif event_type == 'user_removed':
                enrollment = CourseEnrollment.objects.filter(course=course, student_id=user_id, status='active').first()
                if enrollment:
                    enrollment.status = 'dropped'
                    enrollment.save()
                    self.stdout.write(f"Пользователь {user_id} отчислен из курса {course_id}")
                else:
                    self.stdout.write(f"Запись для пользователя {user_id} в курсе {course_id} не найдена или уже отчислена")

            elif event_type == 'course_completed':
                enrollment = CourseEnrollment.objects.filter(course=course, student_id=user_id, status='active').first()
                if enrollment:
                    enrollment.status = 'completed'
                    enrollment.completed_at = timezone.now()
                    enrollment.save()
                    self.stdout.write(f"Пользователь {user_id} завершил курс {course_id}")
                else:
                    self.stdout.write(f"Запись для пользователя {user_id} в курсе {course_id} не найдена или уже завершена/отчислена")
            else:
                self.stdout.write(f"Неизвестный тип события: {event_type}")
