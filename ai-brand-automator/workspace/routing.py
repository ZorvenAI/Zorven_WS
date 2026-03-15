"""
WebSocket URL routing for the workspace app.

Defines the URL pattern for workspace WebSocket connections:
    ws://<host>/ws/workspace/<tenant_id>/
"""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/workspace/(?P<tenant_id>\d+)/$",
        consumers.WorkspaceConsumer.as_asgi(),
    ),
]
