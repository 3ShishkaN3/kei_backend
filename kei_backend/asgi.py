import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kei_backend.settings')
django_asgi_app = get_asgi_application()

import notification_service.routing
import material_service.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            notification_service.routing.websocket_urlpatterns +
            material_service.routing.websocket_urlpatterns
        )
    ),
})
