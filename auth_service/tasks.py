from celery import shared_task
from django.utils import timezone
from .models import ConfirmationCode, User
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
    try:
        now = timezone.now()
        expired_codes = ConfirmationCode.objects.filter(expires_at__lt=now)
        user_ids = set(expired_codes.values_list('user', flat=True))
        
        count_codes = expired_codes.count()
        expired_codes.delete()

        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                if not user.is_active and not user.confirmation_codes.filter(expires_at__gt=now).exists():
                    user_email = user.email
                    user.delete()
                    logger.info(f"Удалён неактивированный аккаунт пользователя {user_email} после очистки кодов.")
            except User.DoesNotExist:
                continue
        
        logger.info(f"Удалено {count_codes} просроченных кодов подтверждения")
        return f"Удалено {count_codes} просроченных кодов подтверждения"
    except Exception as e:
        logger.error(f"Ошибка при очистке кодов: {str(e)}")
        return f"Ошибка: {str(e)}"