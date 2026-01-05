"""
Утилиты для интеграции с django-axes.

Содержит вспомогательные функции для работы с системой
защиты от брутфорс атак django-axes.
"""


def get_axes_username(request, credentials):
    """
    Извлекает username для django-axes из запроса или учетных данных.
    
    Используется для корректной работы django-axes с системой
    аутентификации по username или email.
    
    Args:
        request: HTTP запрос
        credentials (dict): Учетные данные пользователя
        
    Returns:
        str: Нормализованный username в нижнем регистре или None
    """
    username = credentials.get("username")
    if not username:
        username = request.POST.get("username") or request.POST.get("email")
    return username.lower() if username else None
