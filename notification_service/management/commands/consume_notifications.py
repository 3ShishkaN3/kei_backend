import json
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from kafka import KafkaConsumer
from decouple import config
from notification_service.models import Notification

User = get_user_model()

class Command(BaseCommand):
    help = "Прослушивание событий прогресса для создания общих уведомлений"

    def handle(self, *args, **options):
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=lambda v: [s.strip() for s in v.split(',')])
        
        consumer = KafkaConsumer(
            'progress_events', 
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id='notification_service_group',
        )
        
        self.stdout.write(self.style.SUCCESS(f"Notification Service: Начало прослушивания 'progress_events'..."))
        
        for message in consumer:
            data = message.value
            event_type = data.get('type')
            user_id = data.get('user_id')
            
            try:
                user = User.objects.get(pk=user_id)
                
                if event_type == 'lesson_completed':
                    Notification.objects.create(
                        user=user,
                        title="Урок пройден! 🎉",
                        message=f"Вы успешно завершили урок!",
                        notification_type='course',
                    )
                
                elif event_type == 'course_completed':
                    Notification.objects.create(
                        user=user,
                        title="Курс завершен! 🏆",
                        message="Поздравляем! Вы полностью прошли курс. Это выдающийся результат!",
                        notification_type='course',
                    )
                
                elif event_type == 'test_graded':
                    status = data.get('status')
                    score = data.get('score', 0)
                    if status in ['passed', 'auto_passed']:
                        Notification.objects.create(
                            user=user,
                            title="Тест проверен ✅",
                            message=f"Ваш тест проверен! Результат: {score} очков. Отличная работа!",
                            notification_type='system',
                        )
                    else:
                        Notification.objects.create(
                            user=user,
                            title="Тест проверен",
                            message=f"Ваш тест проверен. Результат: {score} очков. Попробуйте еще раз, чтобы улучшить результат!",
                            notification_type='system',
                        )

                elif event_type == 'term_learned':
                    learned_count = user.learned_entries.count()
                    if learned_count in [1, 10, 50, 100, 250, 500, 1000]:
                        Notification.objects.create(
                            user=user,
                            title="Словарный запас растет! 📚",
                            message=f"Вы выучили уже {learned_count} слов! Так держать!",
                            notification_type='system',
                        )

                elif event_type in ['test_graded', 'lesson_completed']:
                    from progress_service.models import LearningStats
                    stats, _ = LearningStats.objects.get_or_create(user=user)
                    # TODO: имплементировать это всё
                    pass

            except User.DoesNotExist:
                continue
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Ошибка создания уведомления: {e}"))
