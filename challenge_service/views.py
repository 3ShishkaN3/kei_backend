import json
import time
import logging
from datetime import datetime

from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.decorators import renderer_classes

from .models import DailyChallenge, ChallengeTest
from .serializers import (
    DailyChallengeDetailSerializer,
    DailyChallengeListSerializer,
    ChallengeStatusSerializer,
)

logger = logging.getLogger(__name__)

COINS_REWARD = 20
STALE_TIMEOUT_MINUTES = 5


class ServerSentEventRenderer(BaseRenderer):
    """Renderer для поддержки Accept: text/event-stream в DRF-view."""
    media_type = 'text/event-stream'
    format = 'event-stream'
    charset = None
    render_style = 'binary'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def _get_today_msk():
    """Получить сегодняшнюю дату по МСК."""
    import pytz
    msk = pytz.timezone('Europe/Moscow')
    return datetime.now(msk).date()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def challenge_status(request):
    """
    GET /api/v1/challenges/status/?course_id=X
    Возвращает статус сегодняшнего испытания.
    """
    course_id = request.query_params.get('course_id')
    if not course_id:
        return Response({'error': 'course_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    today = _get_today_msk()

    try:
        challenge = DailyChallenge.objects.get(
            user=request.user,
            course_id=course_id,
            date=today,
        )

        if challenge.generation_status == 'ready':
            linked_tests_count = ChallengeTest.objects.filter(challenge=challenge).count()
            if linked_tests_count == 0:
                challenge.generation_status = 'failed'
                challenge.generation_error = 'Испытание было отмечено как готовое без заданий. Нужна перегенерация.'
                challenge.total_items = 0
                challenge.save(update_fields=['generation_status', 'generation_error', 'total_items', 'updated_at'])

        if challenge.is_stale_generating(STALE_TIMEOUT_MINUTES):
            challenge.generation_status = 'failed'
            challenge.generation_error = 'Генерация прервана (таймаут).'
            challenge.save(update_fields=['generation_status', 'generation_error', 'updated_at'])

        serializer = ChallengeStatusSerializer(challenge, context={'request': request})
        return Response(serializer.data)

    except DailyChallenge.DoesNotExist:
        return Response({
            'status': 'not_generated',
            'date': str(today),
        })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@renderer_classes([JSONRenderer, ServerSentEventRenderer])
def challenge_generate(request):
    """
    GET /api/v1/challenges/generate/?course_id=X
    SSE-эндпоинт для запуска генерации и стриминга прогресса.
    Идемпотентный: если испытание уже есть — возвращает его статус.
    """
    course_id = request.query_params.get('course_id')
    if not course_id:
        return Response({'error': 'course_id обязателен'}, status=status.HTTP_400_BAD_REQUEST)

    today = _get_today_msk()

    challenge, created = DailyChallenge.objects.get_or_create(
        user=request.user,
        course_id=course_id,
        date=today,
        defaults={
            'generation_status': 'pending',
            'completion_status': 'not_started',
        }
    )

    if challenge.is_stale_generating(STALE_TIMEOUT_MINUTES):
        challenge.generation_status = 'failed'
        challenge.generation_error = 'Генерация прервана (таймаут). Перезапускаем...'
        challenge.save(update_fields=['generation_status', 'generation_error', 'updated_at'])

    if challenge.generation_status == 'ready':
        return Response({
            'event': 'ready',
            'challenge_id': challenge.id,
            'message': 'Испытание уже сгенерировано',
        })

    if challenge.completion_status == 'completed':
        return Response({
            'event': 'completed',
            'challenge_id': challenge.id,
            'message': 'Испытание уже пройдено сегодня',
        })

    if challenge.generation_status == 'failed':
        challenge.generation_status = 'pending'
        challenge.generation_error = ''
        challenge.celery_task_id = ''
        challenge.blitz_quizzes = []
        challenge.total_items = 0
        old_test_ids = list(
            ChallengeTest.objects.filter(challenge=challenge).values_list('test_id', flat=True)
        )
        ChallengeTest.objects.filter(challenge=challenge).delete()
        if old_test_ids:
            from material_service.models import Test
            Test.objects.filter(id__in=old_test_ids, source='daily-challenge').delete()
        challenge.save(update_fields=[
            'generation_status',
            'generation_error',
            'celery_task_id',
            'blitz_quizzes',
            'total_items',
            'updated_at'
        ])
        created = True

    if challenge.generation_status == 'pending':
        from .tasks import generate_daily_challenge_task
        result = generate_daily_challenge_task.delay(challenge.id)
        challenge.celery_task_id = result.id
        challenge.generation_status = 'generating'
        challenge.save(update_fields=['celery_task_id', 'generation_status', 'updated_at'])

    # SSE streaming прогресса
    def event_stream():
        from .tasks import get_challenge_progress
        max_wait = 120
        poll_interval = 1
        elapsed = 0
        last_phase = None

        while elapsed < max_wait:
            progress = get_challenge_progress(challenge.id)

            if progress:
                phase = progress.get('phase', '')
                if phase != last_phase:
                    if phase == 'blitz_done':
                        challenge.refresh_from_db()
                        blitz_data = json.dumps({
                            'event': 'blitz_ready',
                            'quizzes': challenge.blitz_quizzes,
                        }, ensure_ascii=False)
                        yield f"data: {blitz_data}\n\n"

                    progress_data = json.dumps({
                        'event': 'progress',
                        'phase': phase,
                        'percent': progress.get('percent', 0),
                        'message': progress.get('message', ''),
                    }, ensure_ascii=False)
                    yield f"data: {progress_data}\n\n"
                    last_phase = phase

                    if phase == 'ready':
                        challenge.refresh_from_db()
                        ready_data = json.dumps({
                            'event': 'ready',
                            'challenge_id': challenge.id,
                        }, ensure_ascii=False)
                        yield f"data: {ready_data}\n\n"
                        return

                    if phase == 'failed':
                        fail_data = json.dumps({
                            'event': 'failed',
                            'message': progress.get('message', 'Ошибка генерации'),
                        }, ensure_ascii=False)
                        yield f"data: {fail_data}\n\n"
                        return

            time.sleep(poll_interval)
            elapsed += poll_interval

            if elapsed % 10 == 0:
                yield f": heartbeat\n\n"

        yield f"data: {json.dumps({'event': 'timeout', 'message': 'Превышено время ожидания'})}\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def challenge_detail(request, challenge_id):
    """
    GET /api/v1/challenges/{id}/
    Возвращает полные данные испытания с тестами (через TestSerializer).
    """
    try:
        challenge = DailyChallenge.objects.get(
            pk=challenge_id,
            user=request.user,
        )
    except DailyChallenge.DoesNotExist:
        return Response({'error': 'Испытание не найдено'}, status=status.HTTP_404_NOT_FOUND)

    tests_exists = ChallengeTest.objects.filter(challenge=challenge).exists()
    if challenge.generation_status != 'ready' and not tests_exists:
        return Response(
            {'error': 'Испытание ещё не готово', 'generation_status': challenge.generation_status},
            status=status.HTTP_400_BAD_REQUEST
        )

    if challenge.completion_status == 'not_started':
        challenge.completion_status = 'in_progress'
        challenge.save(update_fields=['completion_status', 'updated_at'])

    serializer = DailyChallengeDetailSerializer(challenge, context={'request': request})
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def challenge_complete(request, challenge_id):
    """
    POST /api/v1/challenges/{id}/complete/
    Завершить испытание, подсчитать очки по TestSubmission и начислить монеты.
    """
    try:
        challenge = DailyChallenge.objects.get(
            pk=challenge_id,
            user=request.user,
        )
    except DailyChallenge.DoesNotExist:
        return Response({'error': 'Испытание не найдено'}, status=status.HTTP_404_NOT_FOUND)

    if challenge.completion_status == 'completed':
        return Response({'error': 'Испытание уже завершено'}, status=status.HTTP_400_BAD_REQUEST)

    if challenge.generation_status != 'ready':
        return Response({'error': 'Испытание не готово'}, status=status.HTTP_400_BAD_REQUEST)

    from material_service.models import TestSubmission

    challenge_test_ids = list(
        ChallengeTest.objects.filter(challenge=challenge).values_list('test_id', flat=True)
    )
    total_count = len(challenge_test_ids)

    submissions = TestSubmission.objects.filter(
        test_id__in=challenge_test_ids,
        student=request.user,
    )

    correct_count = 0
    grading_pending = 0
    for sub in submissions:
        if sub.status in ('auto_passed',):
            correct_count += 1
        elif sub.status in ('auto_failed',):
            pass  # не правильный
        elif sub.status == 'graded':
            if sub.score and sub.score >= 0.7:
                correct_count += 1
        elif sub.status == 'grading_pending':
            grading_pending += 1

    score = round((correct_count / total_count * 100) if total_count > 0 else 0)

    challenge.correct_items = correct_count
    challenge.score = score
    challenge.completion_status = 'completed'
    challenge.completed_at = timezone.now()
    challenge.coins_awarded = COINS_REWARD
    challenge.save(update_fields=[
        'correct_items', 'score', 'completion_status',
        'completed_at', 'coins_awarded', 'updated_at',
    ])

    try:
        from progress_service.models import LearningStats
        stats, _ = LearningStats.objects.get_or_create(user=request.user)
        stats.coins += COINS_REWARD
        stats.save(update_fields=['coins'])
    except Exception as e:
        logger.warning(f"Не удалось начислить монеты: {e}")

    return Response({
        'score': score,
        'correct_items': correct_count,
        'total_items': total_count,
        'coins_awarded': COINS_REWARD,
        'completed_at': challenge.completed_at.isoformat(),
        'grading_pending': grading_pending,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def challenge_history(request):
    """
    GET /api/v1/challenges/history/?course_id=X&period=week
    История испытаний для статистики.
    """
    course_id = request.query_params.get('course_id')
    period = request.query_params.get('period', 'week')

    challenges = DailyChallenge.objects.filter(
        user=request.user,
        completion_status='completed',
    )

    if course_id:
        challenges = challenges.filter(course_id=course_id)

    if period == 'week':
        from datetime import timedelta
        since = timezone.now() - timedelta(days=7)
        challenges = challenges.filter(completed_at__gte=since)
    elif period == 'month':
        from datetime import timedelta
        since = timezone.now() - timedelta(days=33)
        challenges = challenges.filter(completed_at__gte=since)

    challenges = challenges.order_by('-date')
    serializer = DailyChallengeListSerializer(challenges, many=True)
    return Response(serializer.data)
