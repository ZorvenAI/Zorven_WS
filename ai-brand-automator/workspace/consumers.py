"""
WebSocket consumer for workspace real-time updates.

Handles per-tenant channel groups for broadcasting:
  - job_progress: Per-node progress updates during pipeline execution
  - job_completed: Terminal job status (completed/failed)

Clients connect to: ws://<host>/ws/workspace/<tenant_id>/?token=<jwt>
"""

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class WorkspaceConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for workspace pipeline progress.

    Joins a per-tenant group on connect. Receives broadcast events
    from the result_handler channel_layer bridge and forwards them
    to connected clients.
    """

    async def connect(self):
        """Authenticate and join the tenant group."""
        self.tenant_id = self.scope["url_route"]["kwargs"].get("tenant_id", "0")
        self.group_name = f"workspace_{self.tenant_id}"

        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            logger.warning(
                "WebSocket connection rejected: unauthenticated (tenant=%s)",
                self.tenant_id,
            )
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info(
            "WebSocket connected: user=%s, tenant=%s, group=%s",
            user.email if hasattr(user, "email") else user,
            self.tenant_id,
            self.group_name,
        )

    async def disconnect(self, close_code):
        """Leave the tenant group on disconnect."""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(
                "WebSocket disconnected: tenant=%s, code=%s",
                self.tenant_id,
                close_code,
            )

    async def receive_json(self, content, **kwargs):
        """Handle incoming messages from the client (ping/pong)."""
        msg_type = content.get("type")
        if msg_type == "ping":
            await self.send_json({"type": "pong"})

    # ── Channel layer event handlers ──

    async def job_progress(self, event):
        """Forward job progress update to the WebSocket client."""
        await self.send_json(
            {
                "type": "job_progress",
                "data": event.get("data", {}),
            }
        )

    async def job_completed(self, event):
        """Forward job completion event to the WebSocket client."""
        await self.send_json(
            {
                "type": "job_completed",
                "data": event.get("data", {}),
            }
        )
