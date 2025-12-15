import os
from django.core.asgi import get_asgi_application

# Сначала мы устанавливаем переменную окружения для настроек Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kei_backend.settings')

# Затем мы вызываем get_asgi_application(). Этот вызов инициализирует Django.
# После этой строки Django полностью готов к работе.
django_asgi_app = get_asgi_application()

# И только теперь, когда Django готов, мы можем безопасно импортировать
# модули, которые зависят от Django (например, наши consumers).
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import kei_backend.routing

application = ProtocolTypeRouter({
    # Для обычных HTTP запросов используется уже инициализированное приложение.
    "http": django_asgi_app,
    
    # Для WebSocket запросов используется наш стек с аутентификацией и маршрутизацией.
    "websocket": AuthMiddlewareStack(
        URLRouter(
            kei_backend.routing.websocket_urlpatterns
        )
    ),
})
