"""Kafka consumer for scheduled trend scan commands."""

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class ScheduledScanConsumer:
    """Consume scheduled scan commands from Kafka."""

    _COMMAND_TOPIC = "agent.commands.trend-cultural-agent"

    def __init__(
        self,
        bootstrap_servers: str,
        executor: Any,
        redis_manager: Any,
        consumer_group: str = "tcia-scheduled-scan-group",
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._executor = executor
        self._redis = redis_manager
        self._consumer_group = consumer_group
        self._consumer: Any = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start consuming."""
        if not self._bootstrap_servers:
            logger.info("Kafka consumer disabled (no bootstrap servers)")
            return
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                self._COMMAND_TOPIC,
                bootstrap_servers=self._bootstrap_servers,
                group_id=self._consumer_group,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            await self._consumer.start()
            self._running = True
            self._task = asyncio.create_task(self._consume_loop())
            logger.info("ScheduledScanConsumer started on %s", self._COMMAND_TOPIC)
        except Exception as exc:
            logger.warning("Failed to start consumer: %s", exc)

    async def _consume_loop(self) -> None:
        """Main consume loop."""
        while self._running and self._consumer:
            try:
                async for message in self._consumer:
                    await self._handle_message(message.value)
            except Exception as exc:
                logger.error("Consumer error: %s", exc)
                if self._running:
                    await asyncio.sleep(5)

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle a scheduled scan command."""
        try:
            command_type = data.get("command_type", "")
            tenant_id = data.get("tenant_id", "")
            payload = data.get("payload", {})
            idem_key = data.get("idempotency_key", "")

            if not tenant_id or not command_type:
                logger.warning("Invalid command: missing tenant_id or type")
                return

            # Idempotency check
            if idem_key and await self._redis.check_idempotency(idem_key):
                logger.info("Skipping duplicate command: %s", idem_key)
                return

            scan_type = payload.get("scan_type", "daily_scan")
            industry = payload.get("industry", "")
            focus_areas = payload.get("focus_areas", [])

            await self._executor.execute(
                prompt=f"Run {scan_type} trend analysis for {industry}",
                input_context={
                    "job_id": str(uuid4()),
                    "scan_type": scan_type,
                },
                tenant_context={"tenant_id": tenant_id},
                config={
                    "scan_type": scan_type,
                    "focus_areas": focus_areas,
                },
                previous_outputs={},
                tenant_id=tenant_id,
            )

            # Mark idempotency
            if idem_key:
                await self._redis.set_idempotency(idem_key, ttl=86400)

        except Exception as exc:
            logger.error("Failed to handle command: %s", exc)

    async def stop(self) -> None:
        """Stop consuming."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
