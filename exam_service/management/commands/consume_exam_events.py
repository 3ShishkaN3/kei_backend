import json
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from decouple import config


class Command(BaseCommand):
    help = "Kafka consumer для событий экзамена (прокторинг камерой)"

    def handle(self, *args, **options):
        bootstrap_servers = config(
            "KAFKA_BOOTSTRAP_SERVERS",
            default="kafka:29092",
            cast=lambda v: [s.strip() for s in v.split(",")]
        )
        group_id = "exam_proctoring_consumer"

        while True:
            consumer = None
            try:
                consumer = KafkaConsumer(
                    "exam_events",
                    bootstrap_servers=bootstrap_servers,
                    group_id=group_id,
                    auto_offset_reset="earliest",
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=3000,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Listening to 'exam_events' topic on {bootstrap_servers}..."
                    )
                )

                for message in consumer:
                    raw_value = message.value
                    try:
                        if isinstance(raw_value, (bytes, bytearray)):
                            text = raw_value.decode("utf-8")
                            data = json.loads(text)
                        elif isinstance(raw_value, str):
                            data = json.loads(raw_value)
                        else:
                            data = raw_value
                    except json.JSONDecodeError as je:
                        self.stdout.write(f"JSON decode error: {je}. Skipping.")
                        continue

                    event_type = data.get("type")
                    self.stdout.write(f"Received event: {event_type}")

                    if event_type == "EXAM_TERMINATED_BY_SYSTEM":
                        self._handle_termination(data)
                    else:
                        self.stdout.write(f"Unknown event type: {event_type}")

            except KafkaError as ke:
                self.stdout.write(f"KafkaError: {ke}. Reconnecting in 5s...")
                if consumer:
                    try:
                        consumer.close()
                    except Exception:
                        pass
                time.sleep(5)
            except Exception as e:
                self.stdout.write(f"Error: {e}. Reconnecting in 5s...")
                if consumer:
                    try:
                        consumer.close()
                    except Exception:
                        pass
                time.sleep(5)

    def _handle_termination(self, data):
        from exam_service.models import ExamAttempt

        exam_id = data.get("exam_id")
        payload = data.get("payload", {})
        reason = payload.get("reason", "unknown")
        total_missing_time = payload.get("total_missing_time", 0)

        if not exam_id:
            self.stdout.write("Termination event without exam_id. Skipping.")
            return

        try:
            attempt = ExamAttempt.objects.get(pk=exam_id, status='in_progress')
        except ExamAttempt.DoesNotExist:
            self.stdout.write(f"No active attempt with id {exam_id}. Skipping.")
            return

        attempt.status = 'terminated_by_proctoring'
        attempt.finished_at = timezone.now()
        attempt.camera_violation_seconds = total_missing_time
        attempt.save(update_fields=['status', 'finished_at', 'camera_violation_seconds'])

        self.stdout.write(
            self.style.WARNING(
                f"Exam attempt {exam_id} TERMINATED by proctoring. "
                f"Reason: {reason}, missing time: {total_missing_time}s"
            )
        )
