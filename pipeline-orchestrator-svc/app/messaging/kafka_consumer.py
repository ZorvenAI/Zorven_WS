"""
Kafka trigger consumer — listens for pipeline dispatch events.

Subscribes to pipeline-trigger-topic and routes messages to the
JobExecutor for execution. This is an alternative to the HTTP
dispatch endpoint.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TriggerConsumer:
    """Kafka consumer for pipeline trigger events."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str = "orchestrator-consumers",
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self._consumer = None
        self._running = False

    async def start(self) -> None:
        """Start the Kafka consumer."""
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                "pipeline-trigger-topic",
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._running = True
            logger.info(
                "Kafka trigger consumer started: %s (group: %s)",
                self.bootstrap_servers,
                self.group_id,
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
            logger.info("Kafka trigger consumer stopped")

    async def consume(self, executor: Any) -> None:
        """
        Consume messages and route to the job executor.

        Runs in an asyncio loop until stopped. Each message is
        deserialized as a DispatchRequest and passed to the executor.
        """
        if self._consumer is None:
            logger.warning("Consumer not started — skipping consume loop")
            return

        from app.api.schemas import DispatchRequest

        logger.info("Starting consume loop for pipeline-trigger-topic")

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

                    request = DispatchRequest(**data)
                    logger.info(
                        "Kafka trigger received for job %s",
                        request.job_id,
                    )

                    # Execute the job (non-blocking via asyncio)
                    import asyncio

                    asyncio.create_task(executor.execute(request))

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
