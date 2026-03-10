"""Audit producer — emits tool call audit events."""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AuditProducer:
    """Emits tool call audit events to odoo-worker-audit-topic.

    Gracefully no-ops when Kafka is unavailable (fail-open).
    """

    TOPIC = "odoo-worker-audit-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Optional[Any] = None

    async def start(self) -> None:
        """Start the Kafka producer if servers are configured."""
        if not self._bootstrap_servers:
            logger.info("Kafka not configured — audit producer disabled")
            return

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            logger.info("Audit producer started")
        except Exception as exc:
            logger.warning("Failed to start audit producer: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping audit producer: %s", exc)
            self._producer = None

    async def send_audit(
        self,
        tenant_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        **extra: Any,
    ) -> None:
        """Send an audit event. No-ops if producer unavailable."""
        if not self._producer:
            return

        event = {
            "service": "odoo-worker-agent",
            "tenant_id": tenant_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "success": success,
            **extra,
        }

        try:
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.debug("Failed to send audit event: %s", exc)
