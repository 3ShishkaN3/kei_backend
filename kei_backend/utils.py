from kafka import KafkaProducer
import json
import logging
from decouple import config, Csv

logger = logging.getLogger(__name__)
producer = None

def get_producer():
    global producer
    if producer is None:
        try:
            bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=Csv())
            
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                request_timeout_ms=5000,
                api_version_auto_timeout_ms=5000,
                retries=3,
                retry_backoff_ms=1000
            )
            logger.info(f"Kafka producer initialized with servers: {bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            producer = None
    return producer


def send_to_kafka(topic, data):
    try:
        kafka_producer = get_producer()
        if kafka_producer is None:
            logger.warning(f"Kafka producer not available, skipping event for topic: {topic}")
            return False
            
        future = kafka_producer.send(topic, value=data)
        record_metadata = future.get(timeout=5)
        logger.info(f"Event sent to Kafka topic {topic} partition {record_metadata.partition} offset {record_metadata.offset}")
        return True
    except Exception as e:
        logger.error(f"Error sending Kafka event for topic {topic}: {e}")
        return False
