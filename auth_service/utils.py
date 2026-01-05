"""
Утилиты для сервиса аутентификации.

Содержит функции для отправки email уведомлений и других вспомогательных операций.
"""

import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_confirmation_email(email, code, purpose):
    """
    Отправляет email с кодом подтверждения.
    
    Отправляет email с кодом подтверждения в зависимости от цели:
    - registration: подтверждение регистрации
    - password_change: смена пароля
    - email_change: смена email
    
    Args:
        email (str): Email адрес получателя
        code (str): Код подтверждения
        purpose (str): Цель отправки (registration, password_change, email_change)
    
    Returns:
        None: Функция логирует результат отправки
    """
    if purpose == "registration":
        subject = "Подтверждение регистрации"
        message = f"Ваш код подтверждения регистрации: {code}"
    elif purpose == "password_change":
        subject = "Смена пароля. Код подтверждения"
        message = f"Ваш код для смены пароля: {code}"
    elif purpose == "email_change":
        subject = "Смена email. Код подтверждения"
        message = f"Ваш код для подтверждения смены email: {code}"
    else:
        subject = "Подтверждение"
        message = f"Ваш код подтверждения: {code}"
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [email],
            fail_silently=False,
        )
        logger.info(f"Письмо успешно отправлено на {email} для {purpose}")
    except Exception as e:
        logger.error(f"Ошибка при отправке письма на {email} для {purpose}: {str(e)}")
