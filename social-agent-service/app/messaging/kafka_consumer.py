"""Kafka consumer for content-published-topic events."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.api.schemas import ExecuteRequest
from app.messaging.schemas import ContentPublishedEvent

if TYPE_CHECKING:
    from app.services.social_executor import SocialExecutor

logger = logging.getLogger(__name__)


class ContentPublishedConsumer:
    """Listens to content-published-topic for automatic social promotion."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        executor: SocialExecutor,
    ) -> None:
        self._servers = bootstrap_servers
        self._topic = topic
        self._executor = executor
        self._running = False

    async def start(self) -> None:
        """Start consuming messages in a loop."""
        if not self._servers:
            logger.info("Kafka consumer disabled (no bootstrap servers)")
            return

        try:
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                self._topic,
                bootstrap_servers=self._servers,
                group_id="social-agent-consumers",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
            )
            await consumer.start()
        except Exception as exc:
            logger.warning("Kafka consumer failed to start: %s", exc)
            return

        self._running = True
        logger.info("Kafka consumer started for topic: %s", self._topic)

        try:
            async for msg in consumer:
                if not self._running:
                    break
                await self._handle_message(msg.value)
        except Exception as exc:
            if self._running:
                logger.error("Kafka consumer error: %s", exc)
        finally:
            await consumer.stop()
            logger.info("Kafka consumer stopped")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Process a content-published event."""
        try:
            event = ContentPublishedEvent(**data)
            logger.info(
                "Received content-published event: blog_id=%s tenant=%s",
                event.blog_id,
                event.tenant_id,
            )
            await self._executor.execute_from_event(event, event.tenant_id)
        except Exception as exc:
            logger.error("Failed to process content-published event: %s", exc)

    def stop(self) -> None:
        """Signal the consumer to stop."""
        self._running = False
