"""
Celery задачи для сервиса аутентификации.

Содержит асинхронные задачи для отправки email уведомлений
и очистки просроченных кодов подтверждения.
"""

from celery import shared_task
from django.utils import timezone
from .models import ConfirmationCode, User
from auth_service.utils import send_confirmation_email
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 5}
)
def send_confirmation_email_task(self, email, code, purpose):
    """
    Асинхронная задача для отправки email с кодом подтверждения.
    
    Отправляет email с кодом подтверждения и логирует результат.
    Используется для избежания блокировки основного потока при отправке email.
    
    Args:
        email (str): Email адрес получателя
        code (str): Код подтверждения
        purpose (str): Цель отправки (registration, password_change, email_change)
    
    Returns:
        None: Задача логирует результат выполнения
    """
    logger.info(f"Начало задачи отправки email: email={email}, purpose={purpose}")
    
    if not all([email, code, purpose]):
        raise ValueError("Один из параметров для отправки письма пустой.")
    
    send_confirmation_email(email, code, purpose)
    # logger.info(f"Email успешно отправлен: {email} для {purpose}")  # Это уже логируется в utils.send_confirmation_email


@shared_task(bind=True)
def cleanup_expired_confirmation_codes(self):
    """
    Асинхронная задача для очистки просроченных кодов подтверждения.
    
    Удаляет просроченные коды подтверждения и неактивированные аккаунты
    пользователей, у которых нет активных кодов подтверждения.
    
    Returns:
        str: Результат выполнения задачи (количество удаленных кодов или ошибка)
    """
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