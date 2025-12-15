import json
import time
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from decouple import config, Csv
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from notification_service.models import Notification

User = get_user_model()

class Command(BaseCommand):
    help = 'Запускает Kafka консьюмер для обработки событий уведомлений.'

    def handle(self, *args, **options):
        # --- ШАГ 1: Настройка ---
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', cast=Csv())
        topic_name = 'notification_events'
        consumer_group_id = 'notification_consumer_group'
        channel_layer = get_channel_layer()

        # --- ШАГ 2: Цикл подключения с повторными попытками ---
        consumer = None
        while consumer is None:
            try:
                self.stdout.write('Попытка подключения к Kafka...')
                consumer = KafkaConsumer(
                    topic_name,
                    group_id=consumer_group_id,
                    bootstrap_servers=bootstrap_servers,
                    value_deserializer=lambda x: json.loads(x.decode('utf-8')),
                    auto_offset_reset='earliest',
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=3000,
                    api_version_auto_timeout_ms=10000 
                )
                self.stdout.write(self.style.SUCCESS('Успешно подключились к Kafka!'))
            except NoBrokersAvailable:
                self.stdout.write(self.style.WARNING('Не удалось подключиться к Kafka. Повтор через 5 секунд...'))
                time.sleep(5)

        # --- ШАГ 3: Основной цикл прослушивания сообщений ---
        self.stdout.write(f"Начинаю слушать топик '{topic_name}'...")
        try:
            for message in consumer:
                event_data = message.value
                self.stdout.write(f"Получено событие: {event_data}")
                
                recipient_id = event_data.get('recipient_id')
                notification_type = event_data.get('type')
                extra_data = event_data.get('data', {})

                if not all([recipient_id, notification_type]):
                    self.stdout.write(self.style.WARNING("В событии отсутствуют recipient_id или type."))
                    continue

                try:
                    recipient = User.objects.get(id=recipient_id)
                except User.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f"Пользователь с ID {recipient_id} не найден в базе данных."))
                    continue

                # Создаем уведомление в базе данных
                notification = Notification.objects.create(
                    recipient=recipient,
                    type=notification_type,
                    data=extra_data
                )
                self.stdout.write(self.style.SUCCESS(f"Уведомление '{notification_type}' создано в БД для {recipient.username}."))

                # Формируем группу и отправляем сообщение через Channels
                group_name = f'notifications_for_user_{recipient.id}'
                
                # Формируем сообщение для фронтенда
                frontend_message = {
                    'type': 'send_notification',
                    'message': {
                        'id': notification.id,
                        'type': notification.type,
                        'data': notification.data,
                        'created_at': notification.created_at.isoformat()
                    }
                }
                
                async_to_sync(channel_layer.group_send)(group_name, frontend_message)
                self.stdout.write(self.style.SUCCESS(f"Уведомление отправлено в WebSocket группу {group_name}"))

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\nОстановка консьюмера...'))
        finally:
            if consumer:
                consumer.close()
                self.stdout.write(self.style.SUCCESS('Соединение с Kafka закрыто.'))
