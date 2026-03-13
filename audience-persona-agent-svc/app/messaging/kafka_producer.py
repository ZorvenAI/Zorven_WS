"""Kafka producers for the Audience Persona Agent.

Two producers:
- TraceProducer: Emits to agent-trace-topic for ThoughtTrace UI
- AuditProducer: Emits to audience-persona-audit-topic for compliance
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TraceProducer:
    """Publishes trace events to agent-trace-topic."""

    TOPIC = "agent-trace-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    async def start(self) -> None:
        """Start the Kafka producer."""
        if not self._bootstrap_servers:
            logger.info("TraceProducer: no bootstrap servers, running in stub mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info("TraceProducer connected to %s", self._bootstrap_servers)
        except Exception as exc:
            logger.warning("TraceProducer failed to start: %s", exc)

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer and self._connected:
            await self._producer.stop()
            self._connected = False

    async def send_trace(self, event: dict[str, Any]) -> None:
        """Send a trace event."""
        if not self._connected:
            return
        try:
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.warning("TraceProducer send failed: %s", exc)

    @property
    def is_connected(self) -> bool:
        return self._connected


class AuditProducer:
    """Publishes audit events to audience-persona-audit-topic."""

    TOPIC = "audience-persona-audit-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    async def start(self) -> None:
        """Start the Kafka producer."""
        if not self._bootstrap_servers:
            logger.info("AuditProducer: no bootstrap servers, running in stub mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info("AuditProducer connected to %s", self._bootstrap_servers)
        except Exception as exc:
            logger.warning("AuditProducer failed to start: %s", exc)

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer and self._connected:
            await self._producer.stop()
            self._connected = False

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send an audit event."""
        if not self._connected:
            return
        try:
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.warning("AuditProducer send failed: %s", exc)

    @property
    def is_connected(self) -> bool:
        return self._connected
