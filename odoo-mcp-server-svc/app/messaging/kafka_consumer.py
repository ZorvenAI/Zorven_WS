"""Kafka consumer — tenant provisioning event listener.

Follows fail-open pattern: Kafka unavailability does not break the service.
"""

import json
import logging
from typing import Any, Callable, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class KafkaConsumer:
    """Async Kafka consumer for tenant provisioning events."""

    PROVISIONING_TOPIC = "tenant-provisioning-topic"

    def __init__(
        self,
        on_tenant_provision: Optional[Callable[[dict[str, Any]], Any]] = None,
    ) -> None:
        self._consumer: Optional[Any] = None
        self._connected = False
        self._running = False
        self._on_tenant_provision = on_tenant_provision

    async def start(self) -> None:
        """Initialize Kafka consumer if bootstrap servers configured."""
        if not settings.KAFKA_BOOTSTRAP_SERVERS:
            logger.info("Kafka consumer disabled (no bootstrap servers)")
            return
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                self.PROVISIONING_TOPIC,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id="odoo-mcp-server",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._connected = True
            logger.info("Kafka consumer connected to %s", self.PROVISIONING_TOPIC)
        except Exception as exc:
            logger.warning("Kafka consumer init failed (non-fatal): %s", exc)
            self._connected = False

    async def stop(self) -> None:
        """Shut down Kafka consumer."""
        self._running = False
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception:
                pass
            self._consumer = None
            self._connected = False

    async def consume_loop(self) -> None:
        """Run the consumer loop (call from background task)."""
        if not self._connected or self._consumer is None:
            return
        self._running = True
        try:
            async for message in self._consumer:
                if not self._running:
                    break
                try:
                    event = message.value
                    logger.info(
                        "Received tenant event: %s",
                        event.get("event_type", "unknown"),
                    )
                    if self._on_tenant_provision:
                        await self._on_tenant_provision(event)
                except Exception as exc:
                    logger.error("Error processing tenant event: %s", exc)
        except Exception as exc:
            logger.warning("Kafka consumer loop ended: %s", exc)
            self._running = False

    @property
    def is_connected(self) -> bool:
        return self._connected
