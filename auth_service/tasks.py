from celery import shared_task
from django.utils import timezone
from .models import ConfirmationCode
from auth_service.utils import send_confirmation_email
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True)
def send_confirmation_email_task(self, email, code, purpose):
    """
    Задача для отправки email с подтверждением.
    """
    try:
        logger.info(f"Отправка email с параметрами: email={email}, code={code}, purpose={purpose}")
        
        if not all([email, code, purpose]):
            raise ValueError("Один из параметров для отправки письма пустой.")
        
        send_confirmation_email(email, code, purpose)
        logger.info(f"Email успешно отправлен: {email} для {purpose}")
    except Exception as e:
        logger.error(f"Ошибка при отправке email {email} для {purpose}: {str(e)}")

@shared_task(bind=True)
def cleanup_expired_confirmation_codes(self):
    """
    Задача для удаления просроченных кодов подтверждения.
    """
    try:
        now = timezone.now()
        expired_codes = ConfirmationCode.objects.filter(expires_at__lt=now)
        count = expired_codes.count()
        expired_codes.delete()
        logger.info(f"Удалено {count} просроченных кодов подтверждения")
        return f"Удалено {count} просроченных кодов подтверждения"
    except Exception as e:
        logger.error(f"Ошибка при очистке кодов: {str(e)}")
        return f"Ошибка: {str(e)}"
