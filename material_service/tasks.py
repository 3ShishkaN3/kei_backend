import logging
import requests
from celery import shared_task
from django.core.files.base import ContentFile
from material_service.models import TestSubmission, PronunciationSubmissionAnswer

logger = logging.getLogger(__name__)

ONSEI_API_URL = "http://onsei-api:8877/compare/score"

@shared_task
def grade_pronunciation_submission(submission_id):
    try:
        submission = TestSubmission.objects.get(id=submission_id)
        if submission.test.test_type != 'pronunciation':
            return
            
        answer = submission.pronunciation_answer
        question = getattr(submission.test, 'pronunciation_question', None)
        
        if not question:
             logger.error(f"Cannot grade pronunciation submission {submission_id}: missing pronunciation_question details on test.")
             submission.status = 'auto_failed'
             submission.feedback = "Ошибка платформы: настройки теста на произношение отсутствуют."
             submission.save(update_fields=['status', 'feedback'])
             return
            
        teacher_audio = question.reference_audio_file
        student_audio = answer.submitted_audio_file
        sentence = question.text_to_pronounce or ""
        
        if not teacher_audio or not student_audio:
            logger.error(f"Cannot grade pronunciation submission {submission_id}: missing audio files.")
            submission.status = 'auto_failed'
            submission.feedback = "Ошибка платформы: отсутствует эталонное аудио или аудио ученика."
            submission.save(update_fields=['status', 'feedback'])
            return

        with teacher_audio.open('rb') as ta, student_audio.open('rb') as sa:
            files = {
                'teacher_audio_file': (teacher_audio.name, ta, 'audio/mpeg'),
                'student_audio_file': (student_audio.name, sa, 'audio/mpeg'),
            }
            data = {
                'sentence': sentence,
                'transcript': question.transcript or "",
                'alignment_method': 'phonemes',
                'fallback_if_no_alignment': 'true'
            }
            response = requests.post(ONSEI_API_URL, files=files, data=data)
            
            if response.status_code == 200:
                result = response.json()
                score = result.get('score', 0)
                submission.score = score / 100.0
                
                if submission.score >= 0.8:
                    submission.status = 'auto_passed'
                else:
                    submission.status = 'auto_failed'
                    
                submission.feedback = f"Точность произношения: {score}%"
                submission.save(update_fields=['status', 'score', 'feedback'])
            else:
                logger.error(f"Onsei API returned {response.status_code}: {response.text}")
                submission.status = 'auto_failed'
                submission.feedback = f"Ошибка обработки речи сервером Onsei."
                submission.save(update_fields=['status', 'feedback'])
                
    except Exception as e:
        logger.error(f"Error grading pronunciation submission {submission_id}: {e}")
        try:
            submission = TestSubmission.objects.get(id=submission_id)
            submission.status = 'auto_failed'
            submission.feedback = "Произошла внутренняя ошибка при проверке произношения."
            submission.save(update_fields=['status', 'feedback'])
        except Exception:
            pass
