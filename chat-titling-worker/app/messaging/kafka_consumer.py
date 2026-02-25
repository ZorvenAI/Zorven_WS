"""
Kafka consumer — listens for chat-titling events.

Subscribes to chat-titling-topic and routes messages to the
TitlingHandler for processing. Gracefully degrades when Kafka
is unavailable.
"""

import json
import logging
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class TitlingConsumer:
    """Kafka consumer for chat titling events."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str = "titling-consumers",
        topic: str = "chat-titling-topic",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topic = topic
        self._consumer: Any = None
        self._running = False

    async def start(self) -> None:
        """Start the Kafka consumer."""
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                self.topic,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._running = True
            logger.info(
                "Kafka titling consumer started: %s (group: %s, topic: %s)",
                self.bootstrap_servers,
                self.group_id,
                self.topic,
            )
        except Exception as exc:
            logger.warning(
                "Kafka consumer failed to start (running HTTP-only): %s",
                exc,
            )
            self._consumer = None

    async def stop(self) -> None:
        """Stop the Kafka consumer."""
        self._running = False
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Kafka titling consumer stopped")

    async def consume(
        self, handler: Callable[..., Awaitable[None]]
    ) -> None:
        """
        Consume messages and route to the handler.

        Runs in an asyncio loop until stopped. Each message is
        deserialized as a TitlingEvent and passed to the handler.
        """
        if self._consumer is None:
            logger.warning("Consumer not started — skipping consume loop")
            return

        from app.messaging.schemas import TitlingEvent

        logger.info("Starting consume loop for %s", self.topic)

        try:
            async for message in self._consumer:
                if not self._running:
                    break

                try:
                    data = message.value
                    if not isinstance(data, dict):
                        logger.warning(
                            "Invalid message format (not a dict): %s",
                            type(data),
                        )
                        continue

                    event = TitlingEvent(**data)
                    logger.info(
                        "Titling event received for session %s",
                        event.session_id,
                    )
                    await handler(event)

                except Exception as exc:
                    logger.error(
                        "Failed to process Kafka message: %s",
                        exc,
                        exc_info=True,
                    )
        except Exception as exc:
            if self._running:
                logger.error(
                    "Kafka consume loop error: %s",
                    exc,
                    exc_info=True,
                )

    @property
    def is_connected(self) -> bool:
        """Check if the consumer is connected."""
        return self._consumer is not None
