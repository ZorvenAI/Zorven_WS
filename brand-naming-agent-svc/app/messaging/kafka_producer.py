"""Kafka producers for NTA service.

Three producers:
- TraceProducer → agent-trace-topic (real-time node progress)
- AuditProducer → nta-naming-audit-topic (audit trail)
- EventProducer → nta-naming-events-topic (naming events)
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class _BaseProducer:
    """Base Kafka producer with graceful degradation."""

    def __init__(self, bootstrap_servers: str, topic: str):
        self._topic = topic
        self._producer = None
        self._bootstrap_servers = bootstrap_servers

    async def start(self):
        """Start producer (stub mode if no bootstrap servers)."""
        if not self._bootstrap_servers:
            logger.info(
                "Kafka producer for %s in stub mode (no bootstrap servers)",
                self._topic,
            )
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode(),
            )
            await self._producer.start()
            logger.info("Kafka producer started for topic: %s", self._topic)
        except Exception as exc:
            logger.warning("Kafka producer start failed for %s: %s", self._topic, exc)
            self._producer = None

    async def stop(self):
        """Stop producer."""
        if self._producer:
            try:
                await self._producer.stop()
            except Exception:
                pass

    async def send(self, data: dict[str, Any]):
        """Send message to topic."""
        if not self._producer:
            return
        try:
            await self._producer.send_and_wait(self._topic, data)
        except Exception as exc:
            logger.warning("Kafka send to %s failed: %s", self._topic, exc)


class TraceProducer(_BaseProducer):
    """Produces real-time node progress to agent-trace-topic."""

    def __init__(self, bootstrap_servers: str):
        super().__init__(bootstrap_servers, "agent-trace-topic")

    async def send_trace(self, data: dict[str, Any]):
        """Send trace event."""
        await self.send(data)


class AuditProducer(_BaseProducer):
    """Produces audit trail to nta-naming-audit-topic."""

    def __init__(self, bootstrap_servers: str):
        super().__init__(bootstrap_servers, "nta-naming-audit-topic")

    async def send_event(self, data: dict[str, Any]):
        """Send audit event."""
        await self.send(data)


class EventProducer(_BaseProducer):
    """Produces naming events to nta-naming-events-topic."""

    def __init__(self, bootstrap_servers: str):
        super().__init__(bootstrap_servers, "nta-naming-events-topic")

    async def send_event(self, data: dict[str, Any]):
        """Send naming event."""
        await self.send(data)
