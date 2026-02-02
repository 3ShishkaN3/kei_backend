import json
from django.db import models
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from kafka import KafkaConsumer
from decouple import config
from achievement_service.engine import RuleEngine
from progress_service.models import UserProgress, LearningStats, CourseProgress
from dict_service.models import UserLearnedEntry
from notification_service.models import Notification

User = get_user_model()

class Command(BaseCommand):
    help = "Прослушивание событий прогресса для проверки достижений"

    def handle(self, *args, **options):
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=lambda v: [s.strip() for s in v.split(',')])
        
        consumer = KafkaConsumer(
            'progress_events', 
            bootstrap_servers=bootstrap_servers,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            group_id='achievement_service_group',
            session_timeout_ms=30000,
            heartbeat_interval_ms=3000
        )
        
        self.stdout.write(self.style.SUCCESS(f"Achievement Service: Начало прослушивания 'progress_events'..."))
        
        for message in consumer:
            data = message.value
            event_type = data.get('type')
            user_id = data.get('user_id')
            
            trigger_map = {
                'lesson_completed': ['ON_LESSON_COMPLETE'],
                'course_completed': ['ON_COURSE_COMPLETE'],
                'test_submitted': ['ON_TEST_PASSED'],
                'test_graded': ['ON_TEST_PASSED'],
                'section_completed': ['ON_SECTION_COMPLETE'],
                'term_learned': ['ON_WORD_LEARNED', 'ON_KANJI_LEARNED', 'ON_TERM_LEARNED'],
                # 'level_up': ['ON_LEVEL_UP']
            }
            
            event_triggers = trigger_map.get(event_type, [])
            if not event_triggers:
                continue

            if event_type in ['test_submitted', 'test_graded']:
                status = data.get('status')
                if status not in ['passed', 'auto_passed']:
                    continue

            try:
                user = User.objects.get(pk=user_id)
                
                for trigger in event_triggers:
                    self.stdout.write(f"Обработка события {event_type} ({trigger}) для пользователя {user_id}")
                    context = self.build_context(user, data, trigger)
                    new_achievements = RuleEngine.check_achievements(user, trigger, context)
                    
                    for ua in new_achievements:
                        self.stdout.write(self.style.SUCCESS(f"ВЫДАНО ДОСТИЖЕНИЕ: {ua.achievement.title} пользователю {user.username}"))
                        
                        try:
                            stats, _ = LearningStats.objects.get_or_create(user=user)
                            stats.add_experience(ua.achievement.xp_reward)
                            stats.total_achievements += 1
                            stats.save()
                            self.stdout.write(f"Начислено {ua.achievement.xp_reward} XP за достижение.")
                            
                            # Create notification
                            Notification.objects.create(
                                user=user,
                                title="Получено новое достижение!",
                                message=f"Поздравляем! Вы получили достижение '{ua.achievement.title}'.",
                                notification_type='achievement',
                            )
                            self.stdout.write(self.style.SUCCESS(f"Создано уведомление для {user.username}"))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Ошибка начисления награды или создания уведомления: {e}"))
            except User.DoesNotExist:
                self.stdout.write(f"Пользователь {user_id} не найден")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Ошибка обработки: {e}"))

    def build_context(self, user, event_data, trigger):
        """
        Собирает контекст (факты) для проверки правил.
        """
        context = {
            'trigger': trigger,
            'event': event_data,
            'user': {}
        }
        
        try:
            up = UserProgress.objects.get(user=user)
            context['user']['total_lessons'] = up.total_lessons_completed
            context['user']['total_tests'] = up.total_tests_passed
            context['user']['total_courses'] = up.total_courses_completed
        except UserProgress.DoesNotExist:
            pass

        try:
            ls = LearningStats.objects.get(user=user)
            context['user']['streak_days'] = ls.current_streak_days
            context['user']['level'] = ls.level
            context['user']['xp'] = ls.experience_points
        except LearningStats.DoesNotExist:
            pass
            
        try:
            # Общее количество выученных слов/кандзи
            learned_entries = UserLearnedEntry.objects.filter(user=user)
            context['user']['total_terms_learned'] = learned_entries.count()
            
            # Для кандзи можно добавить эвристику: если в названии раздела есть "кандзи" или "kanji"
            # Либо просто считать, что это синонимы, если в БД нет четкого разделения.
            # Но попробуем посчитать именно те, что в "кандзи" разделах
            kanji_count = learned_entries.filter(
                models.Q(entry__section__title__icontains='кандзи') | 
                models.Q(entry__section__title__icontains='kanji')
            ).count()
            context['user']['total_kanji_learned'] = kanji_count
            
            # Дублируем на верхний уровень для удобства написания правил
            context['total_terms_learned'] = context['user']['total_terms_learned']
            context['total_kanji_learned'] = kanji_count
            
            # Алиасы для совместимости (если пользователь ввел такие имена в админке)
            context['user']['words_learned'] = context['user']['total_terms_learned']
            context['user']['kanji_learned'] = kanji_count
            context['words_learned'] = context['user']['total_terms_learned']
            context['kanji_learned'] = kanji_count
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error getting learned entries stats: {e}"))
            
        course_id = event_data.get('course_id')
        if course_id:
            try:
                cp = CourseProgress.objects.get(user=user, course_id=course_id)
                context['user']['course_progress'] = float(cp.completion_percentage)
            except CourseProgress.DoesNotExist:
                pass

        return context
