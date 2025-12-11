from django.core.management import BaseCommand
from kafka import KafkaConsumer
from decouple import config
from decouple import Csv
import json


class Command(BaseCommand):
    def handle(self, *args, **options):
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=Csv())
        consumer = KafkaConsumer('notification_events', group_id='notification_events',
        bootstrap_servers=bootstrap_servers, value_deserializer = lambda x: json.loads(x.decode('utf-8')),)



        try:
            self.stdout.write("Консьюмер запущен и слушает топик...")
            for message in consumer:
                event_data = message.value
                print(event_data)
                self.stdout.write(f"Получено событие: {event_data}")
        except KeyboardInterrupt:
            self.stdout.write('Kafka Ос')

        finally:
            consumer.close()
            self.stdout.write('Соединенение с Kafka разорвано')



