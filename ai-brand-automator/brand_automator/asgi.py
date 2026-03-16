"""
ASGI config for brand_automator project.

Supports both HTTP and WebSocket protocols via Django Channels.
WebSocket routes are handled by workspace consumers for real-time
pipeline progress updates.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

# Initialize Django ASGI application early to ensure AppRegistry is populated
# before importing consumers or routing.
django_asgi_app = get_asgi_application()

from workspace.routing import websocket_urlpatterns  # noqa: E402
from workspace.middleware import JWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # JWTAuthMiddleware runs AFTER AuthMiddlewareStack so it can
        # override the session-based user with the JWT-authenticated one.
        "websocket": AuthMiddlewareStack(
            JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        ),
    }
)
