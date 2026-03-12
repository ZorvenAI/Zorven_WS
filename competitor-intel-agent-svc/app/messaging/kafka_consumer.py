"""Kafka consumer for scheduled competitive scan commands.

Consumes from `agent.commands.competitor-intel-agent` topic, parses
ScheduledScanCommand messages, and dispatches them to the CIA executor.
Gracefully degrades when Kafka is unavailable.
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_COMMAND_TOPIC = "agent.commands.competitor-intel-agent"


class ScheduledScanConsumer:
    """Kafka consumer for scheduled competitive scans."""

    def __init__(
        self,
        bootstrap_servers: str,
        consumer_group: str = "competitor-intel-agent-group",
        executor: Any = None,
        redis_manager: Any = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._consumer_group = consumer_group
        self._executor = executor
        self._redis_manager = redis_manager
        self._consumer = None
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_connected(self) -> bool:
        return self._consumer is not None and self._running

    async def start(self) -> None:
        """Start consuming messages."""
        if not self._bootstrap_servers:
            logger.info("Kafka consumer disabled (no bootstrap servers)")
            return

        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                _COMMAND_TOPIC,
                bootstrap_servers=self._bootstrap_servers,
                group_id=self._consumer_group,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            await self._consumer.start()
            self._running = True
            self._task = asyncio.create_task(self._consume_loop())
            logger.info(
                "Kafka consumer started on topic %s (group: %s)",
                _COMMAND_TOPIC,
                self._consumer_group,
            )
        except Exception as exc:
            logger.warning("Failed to start Kafka consumer: %s", exc)
            self._consumer = None

    async def stop(self) -> None:
        """Stop consuming messages."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer:
            try:
                await self._consumer.stop()
            except Exception:
                pass
            self._consumer = None
        logger.info("Kafka consumer stopped")

    async def _consume_loop(self) -> None:
        """Main consumption loop."""
        while self._running and self._consumer:
            try:
                async for message in self._consumer:
                    if not self._running:
                        break
                    await self._handle_message(message.value)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Consumer loop error: %s", exc)
                if self._running:
                    await asyncio.sleep(5)  # Back off before retry

    async def _handle_message(self, data: dict) -> None:
        """Process a single command message."""
        try:
            from app.messaging.command_schemas import ScheduledScanCommand

            command = ScheduledScanCommand(**data)

            # Validate command type
            if command.command_type != "scheduled_competitive_scan":
                logger.debug(
                    "Ignoring command type: %s", command.command_type
                )
                return

            # Validate tenant_id
            if not command.tenant_id:
                logger.warning("Skipping command with empty tenant_id")
                return

            # Idempotency check
            if command.idempotency_key and self._redis_manager:
                try:
                    is_duplicate = await self._redis_manager.check_idempotency(
                        command.idempotency_key
                    )
                    if is_duplicate:
                        logger.info(
                            "Duplicate command %s (key: %s) — skipping",
                            command.command_id,
                            command.idempotency_key,
                        )
                        return
                    await self._redis_manager.set_idempotency(
                        command.idempotency_key, ttl=86400
                    )
                except Exception as exc:
                    logger.warning("Idempotency check failed: %s", exc)

            logger.info(
                "Processing scheduled scan: command_id=%s, tenant_id=%s, type=%s",
                command.command_id,
                command.tenant_id,
                command.payload.scan_type,
            )

            # Dispatch to executor
            if self._executor:
                from app.api.schemas import ExecuteRequest

                request = ExecuteRequest(
                    input_prompt=(
                        f"Scheduled {command.payload.scan_type} competitive scan "
                        f"for {command.payload.industry or 'general'} industry"
                    ),
                    input_context={
                        "job_id": command.command_id,
                        "brand_description": command.payload.brand_description,
                        "industry": command.payload.industry,
                        "geography": command.payload.geography,
                    },
                    tenant_context={
                        "tenant_id": command.tenant_id,
                    },
                    config={
                        "max_competitors": command.payload.max_competitors,
                        "scan_type": command.payload.scan_type,
                    },
                )
                await self._executor.execute(request)

            logger.info("Scheduled scan completed: %s", command.command_id)

        except Exception as exc:
            logger.error("Failed to handle command: %s", exc, exc_info=True)
