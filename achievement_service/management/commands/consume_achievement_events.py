import json
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from kafka import KafkaConsumer
from decouple import config
from achievement_service.engine import RuleEngine
from progress_service.models import UserProgress, LearningStats, CourseProgress

User = get_user_model()

class Command(BaseCommand):
    help = "Прослушивание событий прогресса для проверки достижений"

    def handle(self, *args, **options):
        bootstrap_servers = config('KAFKA_BOOTSTRAP_SERVERS', default='kafka:29092', cast=lambda v: [s.strip() for s in v.split(',')])
        
        # Используем отдельную группу consumer_group, чтобы получать копию сообщений
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
            
            # Маппинг типов событий на триггеры
            trigger_map = {
                'lesson_completed': 'ON_LESSON_COMPLETE',
                'course_completed': 'ON_COURSE_COMPLETE', # Если такое событие есть
                'test_submitted': 'ON_TEST_PASSED', # Проверим статус внутри
                'test_graded': 'ON_TEST_PASSED',
                'section_completed': 'ON_SECTION_COMPLETE',
                # 'level_up': 'ON_LEVEL_UP' # Если будет
            }
            
            trigger = trigger_map.get(event_type)
            if not trigger:
                continue

            # Дополнительная фильтрация для тестов (только пройденные)
            if event_type in ['test_submitted', 'test_graded']:
                status = data.get('status')
                if status not in ['passed', 'auto_passed']:
                    continue

            self.stdout.write(f"Обработка события {event_type} ({trigger}) для пользователя {user_id}")
            
            try:
                user = User.objects.get(pk=user_id)
                context = self.build_context(user, data, trigger)
                
                new_achievements = RuleEngine.check_achievements(user, trigger, context)
                
                for ua in new_achievements:
                    self.stdout.write(self.style.SUCCESS(f"ВЫДАНО ДОСТИЖЕНИЕ: {ua.achievement.title} пользователю {user.username}"))
                    
                    # Начисляем награду за достижение
                    try:
                        stats, _ = LearningStats.objects.get_or_create(user=user)
                        stats.add_experience(ua.achievement.xp_reward)
                        stats.total_achievements += 1
                        stats.save()
                        self.stdout.write(f"Начислено {ua.achievement.xp_reward} XP за достижение.")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Ошибка начисления награды за достижение: {e}"))

                    # Тут можно отправить уведомление в Kafka или WebSocket
                    
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
            'event': event_data, # Включает score, lesson_id, course_id и т.д.
            'user': {}
        }
        
        # Глобальные факты о пользователе
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
            
        # Факты о прогрессе курса (если событие связано с курсом)
        course_id = event_data.get('course_id')
        if course_id:
            try:
                cp = CourseProgress.objects.get(user=user, course_id=course_id)
                context['user']['course_progress'] = float(cp.completion_percentage)
            except CourseProgress.DoesNotExist:
                pass

        return context
