import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kei_backend.settings')
# Initialize Django ASGI application early to ensure its inside AppRegistry
django_asgi_app = get_asgi_application()

import notification_service.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            notification_service.routing.websocket_urlpatterns
        )
    ),
})
