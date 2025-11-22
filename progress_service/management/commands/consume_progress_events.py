import json
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model
from progress_service.models import (
    UserProgress, CourseProgress, LessonProgress, SectionProgress, TestProgress, LearningStats,
    SectionItemView
)
from course_service.models import Course, CourseEnrollment
from lesson_service.models import Lesson, Section, SectionItem
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from decouple import config
from progress_service.tasks import grade_free_text_submission

User = get_user_model()


class Command(BaseCommand):
    help = "Прослушивание событий прогресса из Kafka и обновление данных прогресса"

    def handle(self, *args, **options):
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=lambda v: [s.strip() for s in v.split(',')])
        group_id = config('KAFKA_CONSUMER_GROUP', default='progress_consumer')

        # Подключаемся в цикле с реконнектом при ошибках подключения/работы с Kafka
        while True:
            consumer = None
            try:
                consumer = KafkaConsumer(
                    'progress_events',
                    bootstrap_servers=bootstrap_servers,
                    group_id=group_id,
                    auto_offset_reset='earliest',
                    # Не десериализуем автоматически — будем обрабатывать JSON вручную,
                    # чтобы пропускать некорректные сообщения без падения consumer.
                    session_timeout_ms=30000,
                    heartbeat_interval_ms=3000
                )

                self.stdout.write(self.style.SUCCESS(f"Начало прослушивания топика 'progress_events' с серверами: {bootstrap_servers} (group: {group_id})..."))

                for message in consumer:
                    raw_value = message.value
                    # Попытка безопасной десериализации JSON с обработкой ошибок
                    try:
                        if isinstance(raw_value, (bytes, bytearray)):
                            text = raw_value.decode('utf-8')
                            data = json.loads(text)
                        elif isinstance(raw_value, str):
                            data = json.loads(raw_value)
                        else:
                            # Если сообщение уже разобрано клиентом, используем как есть
                            data = raw_value
                    except json.JSONDecodeError as je:
                        self.stdout.write(
                            f"JSON decode error for message (partition={getattr(message, 'partition', '?')} offset={getattr(message, 'offset', '?')}): {je}. Пропускаю сообщение."
                        )
                        continue

                    event_type = data.get('type')
                    user_id = data.get('user_id')
                    
                    self.stdout.write(f"Получено событие: {event_type} для пользователя {user_id}")
                    
                    try:
                        user = User.objects.get(pk=user_id)
                    except User.DoesNotExist:
                        self.stdout.write(f"Пользователь с id {user_id} не найден")
                        continue
                    
                    try:
                        with transaction.atomic():
                            if event_type == 'lesson_completed':
                                self.handle_lesson_completed(data, user)
                            elif event_type == 'section_completed':
                                self.handle_section_completed(data, user)
                            elif event_type == 'test_submitted':
                                self.handle_test_submitted(data, user)
                            elif event_type == 'test_graded':
                                self.handle_test_graded(data, user)
                            elif event_type == 'material_viewed':
                                self.handle_material_viewed(data, user)
                            else:
                                self.stdout.write(f"Неизвестный тип события: {event_type}")
                    except Exception as e:
                        # Любые другие ошибки при обработке сообщения — логируем и продолжаем
                        self.stdout.write(f"Ошибка обработки события {event_type}: {e}")
                        # не прерываем весь цикл, продолжаем слушать
                        continue

            except KafkaError as ke:
                # Ошибки Kafka — пытаемся реконнектиться
                self.stdout.write(f"KafkaError в consumer: {ke}. Попробую реконнект через 5 секунд...")
                try:
                    if consumer is not None:
                        consumer.close()
                except Exception:
                    pass
                time.sleep(5)
                continue
            except Exception as e:
                # Ошибки при создании consumer или неожиданные ошибки — логируем и реконнектимся
                self.stdout.write(f"Unexpected error in consumer loop: {e}. Реконнект через 5 секунд...")
                try:
                    if consumer is not None:
                        consumer.close()
                except Exception:
                    pass
                time.sleep(5)
                continue

    def handle_lesson_completed(self, data, user):
        """Обработка завершения урока"""
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        
        try:
            lesson = Lesson.objects.get(pk=lesson_id)
        except Lesson.DoesNotExist:
            self.stdout.write(f"Урок с id {lesson_id} не найден")
            return
        
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={
                'total_sections': lesson.sections.count(),
                'completed_sections': lesson.sections.count(),
                'completion_percentage': 100.00,
                'completed_at': timezone.now(),
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            lesson_progress.completed_sections = lesson.sections.count()
            lesson_progress.completion_percentage = 100.00
            lesson_progress.completed_at = timezone.now()
            lesson_progress.last_activity = timezone.now()
            lesson_progress.save()
        
        self.update_user_progress(user)
        
        completed_lessons_count = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests_count = TestProgress.objects.filter(
            user=user, course_id=course_id, status='passed'
        ).values('test_id').distinct().count()
        self.update_course_progress(user, course_id, completed_lessons_count, passed_tests_count)
        
        self.stdout.write(f"Прогресс по уроку {lesson_id} обновлен для пользователя {user.username}")

    def handle_section_completed(self, data, user):
        """Обработка завершения раздела"""
        section_id = data.get('section_id')
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        
        try:
            section = Section.objects.get(pk=section_id)
            lesson = section.lesson
        except Section.DoesNotExist:
            self.stdout.write(f"Раздел с id {section_id} не найден")
            return
        
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={
                'total_sections': lesson.sections.count(),
                'completed_sections': 1,
                'completion_percentage': (1 / lesson.sections.count()) * 100,
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            # Подсчитываем количество завершенных разделов
            completed_sections = Section.objects.filter(
                lesson=lesson,
                completions__student=user
            ).count()
            
            lesson_progress.completed_sections = completed_sections
            lesson_progress.completion_percentage = (completed_sections / lesson.sections.count()) * 100
            lesson_progress.last_activity = timezone.now()
            
            # Если все разделы завершены, отмечаем урок как завершенный
            if completed_sections == lesson.sections.count():
                lesson_progress.completed_at = timezone.now()
            
            lesson_progress.save()
        
        # Обновляем общий прогресс пользователя
        self.update_user_progress(user)
        
        # Обновляем прогресс по курсу
        completed_lessons_count = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests_count = TestProgress.objects.filter(
            user=user, course_id=course_id, status='passed'
        ).values('test_id').distinct().count()
        self.update_course_progress(user, course_id, completed_lessons_count, passed_tests_count)
        
        self.stdout.write(f"Прогресс по разделу {section_id} обновлен для пользователя {user.username}")

    def handle_test_submitted(self, data, user):
        """Обработка отправки теста"""
        test_id = data.get('test_id')
        test_title = data.get('test_title')
        test_type = data.get('test_type')
        section_id = data.get('section_id')
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        submission_id = data.get('submission_id')
        status = data.get('status')
        
        test_progress, created = TestProgress.objects.get_or_create(
            user=user,
            test_id=test_id,
            defaults={
                'test_title': test_title,
                'test_type': test_type,
                'section_id': section_id,
                'lesson_id': lesson_id,
                'course_id': course_id,
                'attempts_count': 1,
                'first_attempt_at': timezone.now(),
                'last_attempt_at': timezone.now(),
                'status': 'in_progress'
            }
        )
        
        if not created:
            test_progress.attempts_count += 1
            test_progress.last_attempt_at = timezone.now()
            
            # Обновляем статус на основе результата
            if status in ['passed', 'auto_passed']:
                test_progress.status = 'passed'
                test_progress.completed_at = timezone.now()
            elif status in ['failed', 'auto_failed']:
                test_progress.status = 'failed'
            
            test_progress.save()
        
        self.update_section_progress(user, section_id)
        
        self.update_lesson_progress(user, lesson_id)
        
        completed_lessons_count = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests_count = TestProgress.objects.filter(
            user=user, course_id=course_id, status='passed'
        ).values('test_id').distinct().count()
        self.update_course_progress(user, course_id, completed_lessons_count, passed_tests_count)
        
        self.update_user_progress(user)
        
        if test_type == 'free-text' and status == 'grading_pending':
            grade_free_text_submission.delay(submission_id)
            self.stdout.write(f"Задача на оценку теста {test_id} для пользователя {user.username} отправлена в очередь.")

        self.stdout.write(f"Прогресс по тесту {test_id} обновлен для пользователя {user.username}")

    def handle_test_graded(self, data, user):
        """Обработка события о завершении ручной/LLM проверки теста."""
        test_id = data.get('test_id')
        status = data.get('status')
        score = data.get('score', 0)

        try:
            test_progress = TestProgress.objects.get(user=user, test_id=test_id)
        except TestProgress.DoesNotExist:
            self.stdout.write(f"TestProgress для теста {test_id} и пользователя {user.username} не найден.")
            return

        # 1. Рассчитываем прирост опыта (только за улучшение результата)
        old_best = test_progress.best_score if test_progress.best_score is not None else 0
        current_score = float(score)
        xp_gain = 0
        
        if current_score > old_best:
            xp_gain = int(current_score - old_best)

        # 2. Обновляем TestProgress
        test_progress.status = 'passed' if status == 'auto_passed' else 'failed'
        test_progress.last_score = score
        if test_progress.best_score is None or score > test_progress.best_score:
            test_progress.best_score = score

        if test_progress.status == 'passed' and not test_progress.completed_at:
            test_progress.completed_at = timezone.now()
        test_progress.save()

        # 3. Начисляем очки опыта и монеты в LearningStats
        if xp_gain > 0:
            try:
                stats, _ = LearningStats.objects.get_or_create(user=user)
                stats.add_experience(xp_gain)
                self.stdout.write(f"Начислено {xp_gain} XP пользователю {user.username}")
            except Exception as e:
                self.stdout.write(f"Ошибка начисления очков опыта для {user.username}: {e}")

        # 3. Запускаем стандартную цепочку обновления прогрессов
        self.update_section_progress(user, data.get('section_id'))
        self.update_lesson_progress(user, data.get('lesson_id'))
        
        course_id = data.get('course_id')
        completed_lessons_count = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests_count = TestProgress.objects.filter(
            user=user, course_id=course_id, status='passed'
        ).values('test_id').distinct().count()
        self.update_course_progress(user, course_id, completed_lessons_count, passed_tests_count)
        self.update_user_progress(user)

        self.stdout.write(f"Прогресс по тесту {test_id} (LLM) обновлен. Начислено {score} очков.")


    def handle_material_viewed(self, data, user):
        """Обработка просмотра нетестового материала"""
        section_item_id = data.get('section_item_id')
        section_id = data.get('section_id')
        lesson_id = data.get('lesson_id')
        course_id = data.get('course_id')
        item_type = (data.get('item_type') or '').lower()

        if item_type == 'test':
            return

        if not all([section_item_id, section_id, lesson_id, course_id]):
            self.stdout.write("Некорректные данные для material_viewed")
            return

        SectionItemView.objects.get_or_create(
            user=user,
            section_item_id=section_item_id,
            defaults={'section_id': section_id}
        )

        self.update_section_progress(user, section_id)
        self.update_lesson_progress(user, lesson_id)

        completed_lessons_count = LessonProgress.objects.filter(
            user=user, lesson__course_id=course_id, completion_percentage=100
        ).count()
        passed_tests_count = TestProgress.objects.filter(
            user=user, course_id=course_id, status='passed'
        ).values('test_id').distinct().count()
        self.update_course_progress(user, course_id, completed_lessons_count, passed_tests_count)
        self.update_user_progress(user)

        self.stdout.write(
            f"Просмотр материала {section_item_id} учтён для пользователя {user.username}"
        )

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
        
        progress.total_courses_enrolled = CourseEnrollment.objects.filter(
            student=user, status='active'
        ).count()
        
        progress.total_courses_completed = CourseEnrollment.objects.filter(
            student=user, status='completed'
        ).count()
        
        progress.total_lessons_completed = LessonProgress.objects.filter(
            user=user, completion_percentage=100
        ).count()
        
        progress.total_sections_completed = SectionProgress.objects.filter(
            user=user, completion_percentage=100
        ).count()
        
        progress.total_tests_passed = TestProgress.objects.filter(
            user=user, status='passed'
        ).count()
        
        progress.total_tests_failed = TestProgress.objects.filter(
            user=user, status='failed'
        ).count()
        
        progress.save()

    def update_section_progress(self, user, section_id):
        """Обновление прогресса по секции с учётом тестов и нетестовых материалов"""
        try:
            section = Section.objects.get(pk=section_id)
        except Section.DoesNotExist:
            return
        
        section_progress, created = SectionProgress.objects.get_or_create(
            user=user,
            section=section,
            defaults={
                'total_items': section.items.count(),
                'total_tests': section.items.filter(item_type='test').count(),
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            section_progress.last_activity = timezone.now()
        
        total_items = section.items.count()
        total_tests = section.items.filter(item_type='test').count()

        passed_tests = TestProgress.objects.filter(
            user=user, section_id=section_id, status='passed'
        ).count()
        failed_tests = TestProgress.objects.filter(
            user=user, section_id=section_id, status='failed'
        ).count()

        total_non_tests = max(0, total_items - total_tests)
        viewed_non_tests = SectionItemView.objects.filter(
            user=user, section_id=section_id
        ).count()
        viewed_non_tests = min(viewed_non_tests, total_non_tests)

        section_progress.total_items = total_items
        section_progress.total_tests = total_tests
        section_progress.passed_tests = passed_tests
        section_progress.failed_tests = failed_tests

        # completed_items = просмотренные нетестовые + пройденные тесты
        section_progress.completed_items = viewed_non_tests + passed_tests

        # Процент завершения по формуле: (просмотренные нетесты + пройденные тесты) / всего элементов
        if total_items > 0:
            section_progress.completion_percentage = (
                section_progress.completed_items / total_items
            ) * 100
        else:
            section_progress.completion_percentage = 0.00
        
        # Если секция завершена, устанавливаем дату завершения
        if section_progress.completion_percentage >= 100 and not section_progress.completed_at:
            section_progress.completed_at = timezone.now()
        
        section_progress.save()

    def update_lesson_progress(self, user, lesson_id):
        """Обновление прогресса по уроку"""
        try:
            lesson = Lesson.objects.get(pk=lesson_id)
        except Lesson.DoesNotExist:
            return
        
        lesson_progress, created = LessonProgress.objects.get_or_create(
            user=user,
            lesson=lesson,
            defaults={
                'last_activity': timezone.now()
            }
        )
        
        if not created:
            lesson_progress.last_activity = timezone.now()
        
        # Подсчитываем статистику по уроку
        lesson_progress.total_sections = lesson.sections.count()
        
        # Подсчитываем завершенные секции
        completed_sections = SectionProgress.objects.filter(
            user=user, section__lesson=lesson, completion_percentage=100
        ).count()
        
        lesson_progress.completed_sections = completed_sections
        
        # Рассчитываем процент завершения: завершенные секции / все секции
        if lesson_progress.total_sections > 0:
            lesson_progress.completion_percentage = (completed_sections / lesson_progress.total_sections) * 100
        else:
            lesson_progress.completion_percentage = 0.00
        
        # Если урок завершен, устанавливаем дату завершения
        if lesson_progress.completion_percentage >= 100 and not lesson_progress.completed_at:
            lesson_progress.completed_at = timezone.now()
        
        lesson_progress.save()

    def update_course_progress(self, user, course_id, completed_lessons_count, passed_tests_count):
        """Обновление прогресса по курсу"""
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return

        course_progress, created = CourseProgress.objects.get_or_create(
            user=user,
            course=course,
            defaults={'last_activity': timezone.now()}
        )

        if not created:
            course_progress.last_activity = timezone.now()

        # Получаем актуальные данные
        total_lessons = course.lessons.count()
        total_tests = SectionItem.objects.filter(section__lesson__course=course, item_type='test').count()
        total_sections = Section.objects.filter(lesson__course=course).count()
        completed_sections = SectionProgress.objects.filter(
            user=user, section__lesson__course=course, completion_percentage=100
        ).count()
        failed_tests = TestProgress.objects.filter(
            user=user, course_id=course.id, status='failed'
        ).values('test_id').distinct().count()

        # Обновляем поля
        course_progress.total_lessons = total_lessons
        course_progress.completed_lessons = completed_lessons_count
        course_progress.total_sections = total_sections
        course_progress.completed_sections = completed_sections
        course_progress.total_tests = total_tests
        course_progress.passed_tests = passed_tests_count
        course_progress.failed_tests = failed_tests

        # Рассчитываем процент завершения
        lessons_completion = (completed_lessons_count / total_lessons * 100) if total_lessons > 0 else 0
        tests_completion = (passed_tests_count / total_tests * 100) if total_tests > 0 else 0
        course_progress.completion_percentage = (lessons_completion + tests_completion) / 2
        
        # Если курс завершен, устанавливаем дату завершения
        if course_progress.completion_percentage >= 100 and not course_progress.completed_at:
            course_progress.completed_at = timezone.now()
        
        course_progress.save()
