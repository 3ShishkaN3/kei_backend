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
    Если у неактивированного пользователя после удаления просроченных кодов
    не остаётся ни одного активного кода подтверждения, то удаляется и аккаунт.
    """
    try:
        now = timezone.now()
        # Получаем просроченные коды подтверждения
        expired_codes = ConfirmationCode.objects.filter(expires_at__lt=now)
        # Сохраняем id пользователей, которым принадлежат просроченные коды
        user_ids = set(expired_codes.values_list('user', flat=True))
        
        count_codes = expired_codes.count()
        # Удаляем просроченные коды подтверждения
        expired_codes.delete()
        
        # Для каждого пользователя, у которого были просроченные коды,
        # проверяем наличие активных кодов. Если пользователь не активирован и
        # не имеет активных кодов, удаляем аккаунт.
        from .models import User  # Импорт модели пользователя
        for user_id in user_ids:
            try:
                user = User.objects.get(id=user_id)
                # Если пользователь не активирован и у него нет активных кодов
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