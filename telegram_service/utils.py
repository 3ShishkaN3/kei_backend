import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def send_telegram_message(message):
    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TEACHER_CHAT_ID
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        logger.info(f"Telegram message sent successfully to chat_id {chat_id}")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {str(e)}")
        raise
