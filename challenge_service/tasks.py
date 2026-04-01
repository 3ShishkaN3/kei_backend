import random
import re
from celery import shared_task
from django.db import transaction
from django.utils import timezone
import json
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _normalize_choice_text(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[。．、,!?！？:：;；\"'`«»()（）\[\]{}]", "", text)
    text = re.sub(r"[\s\u3000]+", "", text)
    return text


def _get_redis_client():
    """Получить Redis-клиент для хранения прогресса генерации."""
    import redis as redis_lib
    return redis_lib.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=0,
        decode_responses=True
    )


def set_challenge_progress(challenge_id, phase, percent, message=''):
    """Записать прогресс генерации в Redis."""
    try:
        r = _get_redis_client()
        progress = json.dumps({
            'phase': phase,
            'percent': percent,
            'message': message,
            'timestamp': timezone.now().isoformat()
        })
        r.setex(
            f'challenge_progress:{challenge_id}',
            300,  # TTL 5 минут
            progress
        )
    except Exception as e:
        logger.warning(f"Не удалось записать прогресс в Redis: {e}")


def get_challenge_progress(challenge_id):
    """Прочитать прогресс генерации из Redis."""
    try:
        r = _get_redis_client()
        data = r.get(f'challenge_progress:{challenge_id}')
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning(f"Не удалось прочитать прогресс из Redis: {e}")
    return None


def _create_test_from_ai_item(item_data, challenge_user):
    """
    Создаёт реальный Test (material_service) из AI-сгенерированного JSON-элемента.
    Возвращает объект Test.
    """
    from material_service.models import (
        Test, MCQOption, FreeTextQuestion,
        WordOrderSentence, MatchingPair,
    )

    item_type = item_data.get('item_type', 'mcq-single')
    title = item_data.get('title', 'Задание')
    question = item_data.get('question', '')
    explanation = item_data.get('explanation', '')

    if item_type in ('mcq-single', 'mcq-multi'):
        test = Test.objects.create(
            title=title,
            description=question,
            test_type=item_type,
            source='daily-challenge',
            created_by=challenge_user,
        )
        options = item_data.get('options', [])
        correct_answer = item_data.get('correct_answer', '')
        correct_answers = item_data.get('correct_answers', [])
        normalized_correct_single = _normalize_choice_text(correct_answer)
        normalized_correct_multi = {
            _normalize_choice_text(answer) for answer in correct_answers
        }
        created_option_ids = []

        for i, opt_text in enumerate(options):
            if item_type == 'mcq-single':
                is_correct = (
                    opt_text.strip() == correct_answer.strip()
                    or _normalize_choice_text(opt_text) == normalized_correct_single
                )
            else:  # mcq-multi
                is_correct = (
                    opt_text.strip() in [ca.strip() for ca in correct_answers]
                    or _normalize_choice_text(opt_text) in normalized_correct_multi
                )

            option = MCQOption.objects.create(
                test=test,
                text=opt_text,
                is_correct=is_correct,
                explanation=explanation if is_correct else '',
                order=i,
            )
            created_option_ids.append(option.id)

        if created_option_ids and not MCQOption.objects.filter(
            test=test, is_correct=True
        ).exists():
            fallback_option = MCQOption.objects.filter(
                id__in=created_option_ids
            ).order_by('order').first()
            if fallback_option:
                fallback_option.is_correct = True
                fallback_option.explanation = explanation
                fallback_option.save(update_fields=['is_correct', 'explanation'])
                logger.warning(
                    "Daily challenge MCQ had no correct option (test_id=%s). Applied fallback to option_id=%s",
                    test.id,
                    fallback_option.id,
                )

    elif item_type == 'word-order':
        correct_order = item_data.get('correct_order', [])
        shuffled = list(correct_order)
        random.shuffle(shuffled)
        attempts = 0
        while shuffled == correct_order and attempts < 10:
            random.shuffle(shuffled)
            attempts += 1

        test = Test.objects.create(
            title=title,
            description=question,
            test_type='word-order',
            source='daily-challenge',
            draggable_options_pool=shuffled,
            created_by=challenge_user,
        )
        WordOrderSentence.objects.create(
            test=test,
            correct_ordered_texts=correct_order,
            explanation=explanation,
        )

    elif item_type == 'drag-and-drop':
        pairs = item_data.get('pairs', [])
        all_answers = [p['answer'] for p in pairs]
        extra_options = [o for o in item_data.get('options', []) if o not in all_answers]
        pool = all_answers + extra_options
        random.shuffle(pool)

        test = Test.objects.create(
            title=title,
            description=question,
            test_type='drag-and-drop',
            source='daily-challenge',
            draggable_options_pool=pool,
            created_by=challenge_user,
        )
        for i, pair in enumerate(pairs):
            MatchingPair.objects.create(
                test=test,
                prompt_text=pair.get('prompt', ''),
                correct_answer_text=pair.get('answer', ''),
                order=i,
                explanation=explanation,
            )

    elif item_type == 'free-text':
        test = Test.objects.create(
            title=title,
            description=question,
            test_type='free-text',
            source='daily-challenge',
            created_by=challenge_user,
        )
        FreeTextQuestion.objects.create(
            test=test,
            reference_answer=item_data.get('correct_answer', ''),
            explanation=explanation,
        )

    else:
        logger.warning(f"Неизвестный тип задания: {item_type}, создаём как mcq-single")
        test = Test.objects.create(
            title=title,
            description=question,
            test_type='mcq-single',
            source='daily-challenge',
            created_by=challenge_user,
        )
        options = item_data.get('options', ['Вариант A', 'Вариант B'])
        correct_answer = item_data.get('correct_answer', options[0] if options else '')
        for i, opt_text in enumerate(options):
            MCQOption.objects.create(
                test=test,
                text=opt_text,
                is_correct=(opt_text.strip() == correct_answer.strip()),
                order=i,
            )

    return test


@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def generate_daily_challenge_task(self, challenge_id):
    """
    Celery-задача для генерации ежедневного испытания.
    Создаёт реальные Test-объекты из material_service.
    Прогресс пишется в Redis.
    """
    from .models import DailyChallenge, ChallengeTest, UserKnowledgeProfile
    from .ai_service import ChallengeAIService

    try:
        challenge = DailyChallenge.objects.select_related('user', 'course').get(pk=challenge_id)

        if challenge.generation_status not in ('pending', 'generating'):
            logger.info(f"Challenge {challenge_id} уже обработан: {challenge.generation_status}")
            return

        challenge.generation_status = 'generating'
        challenge.celery_task_id = self.request.id or ''
        challenge.blitz_quizzes = []
        challenge.total_items = 0
        challenge.save(update_fields=[
            'generation_status',
            'celery_task_id',
            'blitz_quizzes',
            'total_items',
            'updated_at'
        ])

        ai_service = ChallengeAIService()

        set_challenge_progress(challenge_id, 'analyzing', 10, 'Анализируем ваш прогресс...')

        profile, created = UserKnowledgeProfile.objects.get_or_create(
            user=challenge.user,
            course=challenge.course,
            defaults={'profile_data': {}}
        )

        profile_data = ai_service.analyze_user_profile(
            challenge.user,
            challenge.course,
            existing_profile=profile if not created else None
        )

        profile.profile_data = profile_data
        profile.last_analyzed_at = timezone.now()
        profile.save(update_fields=['profile_data', 'last_analyzed_at', 'updated_at'])

        set_challenge_progress(challenge_id, 'analyzing_done', 30, 'Профиль обновлён!')

        set_challenge_progress(challenge_id, 'generating', 35, 'Загружаем испытания...')
        created_count = 0

        for event in ai_service.generate_full_challenge_streamed(challenge.course, profile_data):
            if event['type'] != 'item':
                continue
            item_data = event['data']
            with transaction.atomic():
                test = _create_test_from_ai_item(item_data, challenge.user)
                ChallengeTest.objects.create(
                    challenge=challenge,
                    test=test,
                    order=created_count,
                )
                created_count += 1
                challenge.total_items = created_count
                challenge.save(update_fields=['total_items', 'updated_at'])

            current_percent = min(95, 35 + int((created_count / 15) * 60))
            set_challenge_progress(
                challenge_id,
                'generating',
                current_percent,
                f'Загружаем испытания... {created_count}/15'
            )

            if created_count >= 15:
                break

        if created_count == 0:
            raise ValueError("Нейросеть не вернула заданий для ежедневного испытания")

        challenge.generation_status = 'ready'
        challenge.total_items = created_count
        challenge.save(update_fields=['generation_status', 'total_items', 'updated_at'])

        set_challenge_progress(challenge_id, 'ready', 100, 'Испытание готово!')
        logger.info(f"Challenge {challenge_id} успешно сгенерирован: {created_count} тестов")

    except DailyChallenge.DoesNotExist:
        logger.error(f"DailyChallenge {challenge_id} не найден")
    except Exception as e:
        logger.error(f"Ошибка генерации challenge {challenge_id}: {e}", exc_info=True)
        if self.request.retries < self.max_retries:
            logger.warning(f"Retrying challenge generation {challenge_id} (Attempt {self.request.retries + 1}/{self.max_retries})")
            set_challenge_progress(challenge_id, 'generating', 10, f'Идёт повторная попытка... ({str(e)[:50]})')
        else:
            try:
                challenge = DailyChallenge.objects.get(pk=challenge_id)
                challenge.generation_status = 'failed'
                challenge.generation_error = str(e)[:500]
                challenge.save(update_fields=['generation_status', 'generation_error', 'updated_at'])
            except Exception:
                pass
            set_challenge_progress(challenge_id, 'failed', 0, f'Ошибка: {str(e)[:200]}')

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
