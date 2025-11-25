import json
from decimal import Decimal
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from progress_service.models import (
    UserProgress, CourseProgress, LessonProgress, SectionProgress, TestProgress, LearningStats,
    SectionItemView,
)
from course_service.models import Course, CourseEnrollment
from lesson_service.models import Lesson, Section, SectionItem
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from decouple import config
from progress_service.tasks import grade_free_text_submission
from kei_backend.utils import send_to_kafka

User = get_user_model()


class Command(BaseCommand):
    help = "Прослушивание событий прогресса из Kafka и обновление данных прогресса"

    def handle(self, *args, **options):
        bootstrap_servers = config(
            "KAFKA_BOOTSTRAP_SERVERS", default="kafka:29092", cast=lambda v: [s.strip() for s in v.split(",")]
        )
        group_id = config("KAFKA_CONSUMER_GROUP", default="progress_consumer")

        # Подключаемся в цикле с реконнектом при ошибках подключения/работы с Kafka
        while True:
            consumer = None
            try:
                consumer = KafkaConsumer(
                    "progress_events",
                    bootstrap_servers=bootstrap_servers,
                    group_id=group_id,
                    auto_offset_reset="earliest",
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=3000,
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Начало прослушивания топика 'progress_events' с серверами: {bootstrap_servers} (group: {group_id})..."
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
                        self.stdout.write(
                            f"JSON decode error for message (partition={getattr(message, 'partition', '?')} offset={getattr(message, 'offset', '?')}): {je}. Пропускаю сообщение."
                        )
                        continue

                    event_type = data.get("type")
                    user_id = data.get("user_id")

                    self.stdout.write(f"Получено событие: {event_type} для пользователя {user_id}")

                    try:
                        user = User.objects.get(pk=user_id)
                    except User.DoesNotExist:
                        self.stdout.write(f"Пользователь с id {user_id} не найден")
                        continue

                    try:
                        with transaction.atomic():
                            if event_type == "lesson_completed":
                                self.handle_lesson_completed(data, user)
                            elif event_type == "section_completed":
                                self.handle_section_completed(data, user)
                            elif event_type == "test_submitted":
                                self.handle_test_submitted(data, user)
                            elif event_type == "test_graded":
                                self.handle_test_graded(data, user)
                            elif event_type == "material_viewed":
                                self.handle_material_viewed(data, user)
                            else:
                                self.stdout.write(f"Неизвестный тип события: {event_type}")
                    except Exception as e:
                        self.stdout.write(f"Ошибка обработки события {event_type}: {e}")
                        continue

            except KafkaError as ke:
                self.stdout.write(f"KafkaError в consumer: {ke}. Попробую реконнект через 5 секунд...")
                try:
                    if consumer is not None:
                        consumer.close()
                except Exception:
                    pass
                time.sleep(5)
                continue
            except Exception as e:
                self.stdout.write(f"Unexpected error in consumer loop: {e}. Реконнект через 5 секунд...")
                try:
                    if consumer is not None:
                        consumer.close()
                except Exception:
                    pass
                time.sleep(5)
                continue

    def handle_lesson_completed(self, data, user):
        """Placeholder implementation"""
        self.stdout.write("handle_lesson_completed called (no-op)")

    def handle_section_completed(self, data, user):
        """Placeholder implementation"""
        self.stdout.write("handle_section_completed called (no-op)")

    def handle_material_viewed(self, data, user):
        """Placeholder implementation"""
        self.stdout.write("handle_material_viewed called (no-op)")

    def handle_test_submitted(self, data, user):
        """Обработка отправки теста"""
        test_id = data.get("test_id")
        test_title = data.get("test_title")
        test_type = data.get("test_type")
        section_id = data.get("section_id")
        lesson_id = data.get("lesson_id")
        course_id = data.get("course_id")
        submission_id = data.get("submission_id")
        status = data.get("status")

        test_progress, created = TestProgress.objects.get_or_create(
            user=user,
            test_id=test_id,
            defaults={
                "test_title": test_title,
                "test_type": test_type,
                "section_id": section_id,
                "lesson_id": lesson_id,
                "course_id": course_id,
                "attempts_count": 1,
                "first_attempt_at": timezone.now(),
                "last_attempt_at": timezone.now(),
                "status": "in_progress",
            },
        )

        if not created:
            test_progress.attempts_count += 1
            test_progress.last_attempt_at = timezone.now()
            if status in ["passed", "auto_passed"]:
                test_progress.status = "passed"
                test_progress.completed_at = timezone.now()
            elif status in ["failed", "auto_failed"]:
                test_progress.status = "failed"
            test_progress.save()

        self.update_section_progress(user, section_id)
        self.update_lesson_progress(user, lesson_id, course_id)
        completed_lessons = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests = TestProgress.objects.filter(
            user=user, course_id=course_id, status="passed"
        ).values("test_id").distinct().count()
        self.update_course_progress(user, course_id, completed_lessons, passed_tests)
        self.update_user_progress(user)

        if test_type == "free-text" and status == "grading_pending":
            grade_free_text_submission.delay(submission_id)
            self.stdout.write(
                f"Задача на оценку теста {test_id} для пользователя {user.username} отправлена в очередь."
            )

        self.stdout.write(f"Прогресс по тесту {test_id} обновлен для пользователя {user.username}")

    def handle_test_graded(self, data, user):
        """Обработка события о завершении проверки теста (ручной или LLM)."""
        test_id = data.get("test_id")
        status = data.get("status")
        score = data.get("score", 0)
        section_id = data.get("section_id")
        lesson_id = data.get("lesson_id")
        course_id = data.get("course_id")

        try:
            test_progress = TestProgress.objects.get(user=user, test_id=test_id)
        except TestProgress.DoesNotExist:
            self.stdout.write(f"TestProgress для теста {test_id} и пользователя {user.username} не найден.")
            return

        # Приводим оценку к Decimal для совместимых арифметических операций
        score_decimal = Decimal(str(score))
        
        # Явно преобразуем best_score к Decimal, даже если он уже должен быть Decimal
        if test_progress.best_score is not None:
            old_best = Decimal(str(test_progress.best_score))
        else:
            old_best = Decimal("0")
            
        xp_gain = int(score_decimal - old_best) if score_decimal > old_best else 0

        # Обновляем поля TestProgress
        test_progress.last_score = score_decimal
        if test_progress.best_score is None or score_decimal > Decimal(str(test_progress.best_score)):
            test_progress.best_score = score_decimal
        test_progress.status = "passed" if status in ["passed", "auto_passed"] else "failed"
        if test_progress.status == "passed" and not test_progress.completed_at:
            test_progress.completed_at = timezone.now()
        test_progress.save()

        # Начисляем опыт, если получен прирост
        if xp_gain > 0:
            stats, _ = LearningStats.objects.get_or_create(user=user)
            stats.add_experience(xp_gain)
            self.stdout.write(f"Начислено {xp_gain} XP пользователю {user.username}")

        # Обновляем связанные прогрессы
        self.update_section_progress(user, section_id)
        self.update_lesson_progress(user, lesson_id, course_id)
        completed_lessons = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests = TestProgress.objects.filter(
            user=user, course_id=course_id, status="passed"
        ).values("test_id").distinct().count()
        self.update_course_progress(user, course_id, completed_lessons, passed_tests)
        self.update_user_progress(user)

        self.stdout.write(f"Прогресс по тесту {test_id} (LLM) обновлен. Начислено {score} очков.")

    def update_user_progress(self, user):
        progress, created = UserProgress.objects.get_or_create(
            user=user,
            defaults={"last_activity": timezone.now()},
        )
        if not created:
            progress.last_activity = timezone.now()
        progress.total_courses_enrolled = CourseEnrollment.objects.filter(
            student=user, status="active"
        ).count()
        progress.total_courses_completed = CourseEnrollment.objects.filter(
            student=user, status="completed"
        ).count()
        progress.total_lessons_completed = LessonProgress.objects.filter(
            user=user, completion_percentage=100
        ).count()
        progress.total_sections_completed = SectionProgress.objects.filter(
            user=user, completion_percentage=100
        ).count()
        progress.total_tests_passed = TestProgress.objects.filter(
            user=user, status="passed"
        ).count()
        progress.total_tests_failed = TestProgress.objects.filter(
            user=user, status="failed"
        ).count()
        progress.save()

    def update_section_progress(self, user, section_id):
        try:
            section = Section.objects.get(pk=section_id)
        except Section.DoesNotExist:
            return
        section_progress, created = SectionProgress.objects.get_or_create(
            user=user,
            section=section,
            defaults={
                "total_items": section.items.count(),
                "total_tests": section.items.filter(item_type="test").count(),
                "last_activity": timezone.now(),
            },
        )
        if not created:
            section_progress.last_activity = timezone.now()
        total_items = section.items.count()
        total_tests = section.items.filter(item_type="test").count()
        passed_tests = TestProgress.objects.filter(user=user, section_id=section_id, status="passed").count()
        failed_tests = TestProgress.objects.filter(user=user, section_id=section_id, status="failed").count()
        total_non_tests = max(0, total_items - total_tests)
        viewed_non_tests = SectionItemView.objects.filter(user=user, section_id=section_id).count()
        viewed_non_tests = min(viewed_non_tests, total_non_tests)
        section_progress.total_items = total_items
        section_progress.total_tests = total_tests
        section_progress.passed_tests = passed_tests
        section_progress.failed_tests = failed_tests
        section_progress.completed_items = viewed_non_tests + passed_tests
        if total_items > 0:
            section_progress.completion_percentage = (section_progress.completed_items / total_items) * 100
        else:
            section_progress.completion_percentage = 0.00
        if section_progress.completion_percentage >= 100 and not section_progress.completed_at:
            section_progress.completed_at = timezone.now()
        section_progress.save()

    def update_lesson_progress(self, user, lesson_id, course_id):
        try:
            lesson = Lesson.objects.get(pk=lesson_id)
        except Lesson.DoesNotExist:
            return
        
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={"last_activity": timezone.now()},
        )
        
        was_completed = lesson_progress.completion_percentage >= 100
        
        if not created:
            lesson_progress.last_activity = timezone.now()
        lesson_progress.total_sections = lesson.sections.count()
        completed_sections = SectionProgress.objects.filter(
            user=user, section__lesson=lesson, completion_percentage=100
        ).count()
        lesson_progress.completed_sections = completed_sections
        if lesson_progress.total_sections > 0:
            lesson_progress.completion_percentage = (completed_sections / lesson_progress.total_sections) * 100
        else:
            lesson_progress.completion_percentage = 0.00
        if lesson_progress.completion_percentage >= 100 and not lesson_progress.completed_at:
            lesson_progress.completed_at = timezone.now()
        lesson_progress.save()
        
        # Если урок только что завершился (не был завершен раньше), отправляем событие
        if not was_completed and lesson_progress.completion_percentage >= 100:
            try:
                kafka_data = {
                    'type': 'lesson_completed',
                    'user_id': user.id,
                    'lesson_id': lesson.id,
                    'course_id': course_id,
                    'timestamp': timezone.now().isoformat(),
                }
                send_to_kafka('progress_events', kafka_data)
                self.stdout.write(f"Отправлено событие lesson_completed для урока {lesson.id} пользователя {user.username}")
            except Exception as e:
                self.stdout.write(f"Ошибка отправки события lesson_completed: {e}")

    def update_course_progress(self, user, course_id, completed_lessons_count, passed_tests_count):
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return
        course_progress, created = CourseProgress.objects.get_or_create(
            user=user,
            course=course,
            defaults={"last_activity": timezone.now()},
        )
        if not created:
            course_progress.last_activity = timezone.now()
        total_lessons = course.lessons.count()
        total_tests = SectionItem.objects.filter(section__lesson__course=course, item_type="test").count()
        total_sections = Section.objects.filter(lesson__course=course).count()
        completed_sections = SectionProgress.objects.filter(
            user=user, section__lesson__course=course, completion_percentage=100
        ).count()
        failed_tests = TestProgress.objects.filter(
            user=user, course_id=course.id, status="failed"
        ).values("test_id").distinct().count()
        course_progress.total_lessons = total_lessons
        course_progress.completed_lessons = completed_lessons_count
        course_progress.total_sections = total_sections
        course_progress.completed_sections = completed_sections
        course_progress.total_tests = total_tests
        course_progress.passed_tests = passed_tests_count
        course_progress.failed_tests = failed_tests
        if total_lessons > 0:
            lessons_completion = (completed_lessons_count / total_lessons) * 100
        else:
            lessons_completion = 0
        if total_tests > 0:
            tests_completion = (passed_tests_count / total_tests) * 100
        else:
            tests_completion = 0
        course_progress.completion_percentage = (lessons_completion + tests_completion) / 2
        if course_progress.completion_percentage >= 100 and not course_progress.completed_at:
            course_progress.completed_at = timezone.now()
        course_progress.save()
