import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kei_backend.settings")

# Initialize Django ASGI application early to ensure ORM/model loading works
_django_asgi_app = get_asgi_application()

import material_service.routing  # noqa  E402  pylint: disable=wrong-import-position

application = ProtocolTypeRouter(
    {
        "http": _django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(material_service.routing.websocket_urlpatterns)
        ),
    }
)
