"""Trace producer — emits PAOR step events for real-time UI."""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TraceProducer:
    """Emits step-by-step PAOR events to agent-trace-topic.

    Gracefully no-ops when Kafka is unavailable (fail-open).
    """

    TOPIC = "agent-trace-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Optional[Any] = None

    async def start(self) -> None:
        """Start the Kafka producer if servers are configured."""
        if not self._bootstrap_servers:
            logger.info("Kafka not configured — trace producer disabled")
            return

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            logger.info("Trace producer started")
        except Exception as exc:
            logger.warning("Failed to start trace producer: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping trace producer: %s", exc)
            self._producer = None

    async def send_trace(
        self,
        tenant_id: str,
        phase: str,
        step: int,
        message: str,
        **extra: Any,
    ) -> None:
        """Send a trace event. No-ops if producer unavailable."""
        if not self._producer:
            return

        event = {
            "service": "odoo-worker-agent",
            "tenant_id": tenant_id,
            "phase": phase,
            "step": step,
            "message": message,
            **extra,
        }

        try:
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.debug("Failed to send trace event: %s", exc)
