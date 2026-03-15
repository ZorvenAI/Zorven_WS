"""
WebSocket JWT authentication middleware for Django Channels.

Extracts and validates JWT token from the WebSocket query string
(?token=<jwt>) and sets scope["user"] for downstream consumers.
"""

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_str):
    """Decode JWT access token and return the corresponding user."""
    try:
        token = AccessToken(token_str)
        user_id = token.get(settings.SIMPLE_JWT.get("USER_ID_CLAIM", "user_id"))
        return User.objects.get(pk=user_id)
    except Exception as exc:
        logger.debug("WebSocket JWT auth failed: %s", exc)
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    """Middleware that authenticates WebSocket connections via JWT query param.

    Usage in ASGI routing:
        JWTAuthMiddleware(AuthMiddlewareStack(URLRouter(...)))

    The client connects with: ws://host/ws/workspace/1/?token=<jwt>
    """

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        params = parse_qs(query_string)
        token_list = params.get("token", [])

        if token_list:
            scope["user"] = await get_user_from_token(token_list[0])
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
