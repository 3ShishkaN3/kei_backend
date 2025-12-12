import json
import time
from django.core.management.base import BaseCommand
from decouple import config, Csv
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from notification_service.models import Notification
from auth_service.models import User

class Command(BaseCommand):
    help = 'Запускает Kafka консьюмер для обработки событий уведомлений.'

    def handle(self, *args, **options):
        # --- ШАГ 1: Настройка ---
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', cast=Csv())
        topic_name = 'notification_events'
        consumer_group_id = 'notification_consumer_group' # Используем уникальный group_id

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
                    # Этот таймаут важен для первой попытки подключения
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
                event_data.get('recipient_id', None)
                event_data.get('type', None)
                event_data.get('data', None)
                # TODO: Здесь будет логика обработки события (например, сохранение в базу)

        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\nОстановка консьюмера...'))
        finally:
            if consumer:
                consumer.close()
                self.stdout.write(self.style.SUCCESS('Соединение с Kafka закрыто.'))