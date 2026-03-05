"""Kafka producer — audit and tenant event publishing.

Follows fail-open pattern: Kafka unavailability does not break the service.
"""

import json
import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Async Kafka producer for Odoo MCP audit and tenant events."""

    AUDIT_TOPIC = "odoo-mcp-audit-topic"
    TENANT_EVENTS_TOPIC = "odoo-tenant-events-topic"

    def __init__(self) -> None:
        self._producer: Optional[Any] = None
        self._connected = False

    async def start(self) -> None:
        """Initialize Kafka producer if bootstrap servers configured."""
        if not settings.KAFKA_BOOTSTRAP_SERVERS:
            logger.info("Kafka disabled (no bootstrap servers configured)")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info("Kafka producer connected")
        except Exception as exc:
            logger.warning("Kafka producer init failed (non-fatal): %s", exc)
            self._connected = False

    async def stop(self) -> None:
        """Shut down Kafka producer."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception:
                pass
            self._producer = None
            self._connected = False

    async def publish_audit(self, event: dict[str, Any]) -> None:
        """Publish an audit event (tool call, RBAC decision, etc.)."""
        await self._publish(self.AUDIT_TOPIC, event)

    async def publish_tenant_event(self, event: dict[str, Any]) -> None:
        """Publish a tenant lifecycle event."""
        await self._publish(self.TENANT_EVENTS_TOPIC, event)

    async def _publish(self, topic: str, event: dict[str, Any]) -> None:
        """Publish to a topic (fail-open)."""
        if not self._connected or self._producer is None:
            return
        try:
            await self._producer.send_and_wait(topic, event)
        except Exception as exc:
            logger.warning("Kafka publish to %s failed (non-fatal): %s", topic, exc)

    @property
    def is_connected(self) -> bool:
        return self._connected
