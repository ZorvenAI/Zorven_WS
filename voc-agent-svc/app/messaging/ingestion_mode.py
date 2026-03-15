"""Ingestion mode manager for Kafka↔polling transitions.

Manages transitions between kafka → polling → inactive modes.
Checks Kafka health periodically and logs EVT-021 on mode switches.
"""

import asyncio
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class IngestionModeManager:
    """Manages Kafka↔polling mode for continuous ingestion."""

    def __init__(
        self,
        redis_manager: Any,
        event_emitter: Any,
        kafka_consumer: Any | None = None,
        ingestion_poller: Any | None = None,
    ) -> None:
        self._redis = redis_manager
        self._emitter = event_emitter
        self._kafka_consumer = kafka_consumer
        self._poller = ingestion_poller
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, tenant_id: str) -> None:
        """Start mode management loop."""
        self._running = True
        self._task = asyncio.create_task(
            self._health_check_loop(tenant_id)
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _health_check_loop(self, tenant_id: str) -> None:
        """Periodically check Kafka health and switch modes."""
        interval = settings.INGESTION_KAFKA_HEALTH_CHECK_INTERVAL
        while self._running:
            try:
                current_mode = (
                    await self._redis.get_ingestion_mode(tenant_id)
                    or "inactive"
                )
                kafka_healthy = self._is_kafka_healthy()

                if current_mode == "kafka" and not kafka_healthy:
                    await self._switch_mode(
                        tenant_id, "kafka", "polling"
                    )
                elif current_mode == "polling" and kafka_healthy:
                    await self._switch_mode(
                        tenant_id, "polling", "kafka"
                    )
            except Exception as exc:
                logger.warning("Mode check error: %s", exc)
            await asyncio.sleep(interval)

    def _is_kafka_healthy(self) -> bool:
        """Check if Kafka consumer is healthy."""
        if not self._kafka_consumer:
            return False
        return (
            hasattr(self._kafka_consumer, "_consumer")
            and self._kafka_consumer._consumer is not None
            and self._kafka_consumer._running
        )

    async def _switch_mode(
        self, tenant_id: str, from_mode: str, to_mode: str
    ) -> None:
        """Switch ingestion mode and log EVT-021."""
        logger.info(
            "Switching ingestion mode: %s → %s (tenant=%s)",
            from_mode,
            to_mode,
            tenant_id,
        )
        await self._redis.set_ingestion_mode(tenant_id, to_mode)

        if self._emitter:
            from app.events.catalog import EventType

            await self._emitter.emit(
                EventType.INGESTION_MODE_SWITCH,
                tenant_id=tenant_id,
                data={
                    "from_mode": from_mode,
                    "to_mode": to_mode,
                },
            )

        # Start/stop polling as needed
        if to_mode == "polling" and self._poller:
            await self._poller.start(tenant_id)
        elif from_mode == "polling" and self._poller:
            await self._poller.stop()
