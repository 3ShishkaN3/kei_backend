from kafka import KafkaProducer
import json
from decouple import config, Csv

producer = None

def get_producer():
    global producer
    if producer is None:
        producer = KafkaProducer(
            bootstrap_servers=config('KAFKA_BOOTSTRAP_SERVERS', default='localhost:9092', cast=Csv()),
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
    return producer


def send_to_kafka(topic, data):
    kafka_producer = get_producer()
    kafka_producer.send(topic, value=data)
    kafka_producer.flush()
