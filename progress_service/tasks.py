from celery import shared_task
from django.db import transaction
from django.utils import timezone
import logging

from .llm_service import LLMGradingService
from .models import LearningStats
from material_service.models import TestSubmission, FreeTextSubmissionAnswer, Test
from kei_backend.utils import send_to_kafka

logger = logging.getLogger(__name__)

@shared_task
def grade_free_text_submission(submission_id):
    """
    Асинхронная задача для оценки текстового ответа с помощью LLM.
    Обновляет TestSubmission и отправляет новое событие 'test_graded' в Kafka.
    """
    try:
        with transaction.atomic():
            # Блокируем запись TestSubmission, чтобы избежать гонки состояний
            submission = TestSubmission.objects.select_for_update().get(pk=submission_id)

            # Проверяем, что это текстовый тест и он еще не оценен
            if submission.test.test_type != 'free-text' or submission.status != 'grading_pending':
                logger.warning(f"Попытка оценить уже обработанный или неверный submission_id: {submission_id}")
                return

            # Получаем все необходимые данные
            student_answer_obj = FreeTextSubmissionAnswer.objects.get(submission=submission)
            student_answer = student_answer_obj.answer_text
            
            test = submission.test
            task_text = test.title # Текст задания
            correct_answer = test.free_text_question.reference_answer # Эталонный ответ

            # Инициализируем и вызываем сервис LLM
            llm_service = LLMGradingService()
            grading_result = llm_service.grade_answer(
                task_text=task_text,
                student_answer=student_answer,
                correct_answer=correct_answer
            )

            # 1. Обновляем TestSubmission
            score = grading_result.get('score', 20)
            is_correct = grading_result.get('is_correct', False)
            llm_feedback = grading_result.get('feedback', 'Комментарий отсутствует.')

            submission.score = score
            submission.feedback = f"""{llm_feedback}\n\nОтвет преподавателя: {correct_answer}"""
            submission.status = 'auto_passed' if is_correct else 'auto_failed'
            submission.save()

            # 2. Отправляем событие в Kafka для обновления прогресса
            kafka_data = {
                'type': 'test_graded',
                'user_id': submission.student.id,
                'test_id': test.id,
                'status': submission.status,
                'score': score, # Передаем score как есть (100, 50, или 20)
                'section_id': submission.section_item.section.id,
                'lesson_id': submission.section_item.section.lesson.id,
                'course_id': submission.section_item.section.lesson.course.id,
                'timestamp': timezone.now().isoformat(),
            }
            send_to_kafka('progress_events', kafka_data)

            logger.info(f"Submission {submission_id} успешно оценен LLM и отправлено событие 'test_graded'.")

    except TestSubmission.DoesNotExist:
        logger.error(f"TestSubmission с id={submission_id} не найден.")
    except FreeTextSubmissionAnswer.DoesNotExist:
        logger.error(f"Ответ студента для TestSubmission с id={submission_id} не найден.")
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при оценке submission_id {submission_id}: {e}")
        raise
