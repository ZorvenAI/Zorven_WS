"""Kafka producers for TCIA: trace, audit, and alert streaming."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class TraceProducer:
    """Emit per-node trace events to agent-trace-topic."""

    TOPIC = "agent-trace-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    async def start(self) -> None:
        if not self._bootstrap_servers:
            logger.info("TraceProducer: no bootstrap servers, stub mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
        except Exception as exc:
            logger.warning("TraceProducer failed to start: %s", exc)

    async def send_trace(self, event: dict[str, Any]) -> None:
        if not self._connected:
            return
        try:
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.warning("TraceProducer send failed: %s", exc)

    async def send_step(
        self, job_id: str, message: str, status: str = "PROCESSING"
    ) -> None:
        """Convenience method for step-level trace events."""
        await self.send_trace(
            {
                "job_id": job_id,
                "agent": "trend-cultural-insights",
                "message": message,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def stop(self) -> None:
        if self._producer and self._connected:
            await self._producer.stop()
            self._connected = False


class AuditProducer:
    """Emit audit events to tcia-trend-audit-topic."""

    TOPIC = "tcia-trend-audit-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    async def start(self) -> None:
        if not self._bootstrap_servers:
            logger.info("AuditProducer: no bootstrap servers, stub mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
        except Exception as exc:
            logger.warning("AuditProducer failed to start: %s", exc)

    async def send_event(self, event: dict[str, Any]) -> None:
        if not self._connected:
            return
        try:
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.warning("AuditProducer send failed: %s", exc)

    async def stop(self) -> None:
        if self._producer and self._connected:
            await self._producer.stop()
            self._connected = False


class AlertProducer:
    """Emit opportunity alerts to tcia-trend-alerts-topic."""

    TOPIC = "tcia-trend-alerts-topic"

    def __init__(self, bootstrap_servers: str = "") -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    async def start(self) -> None:
        if not self._bootstrap_servers:
            logger.info("AlertProducer: no bootstrap servers, stub mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
        except Exception as exc:
            logger.warning("AlertProducer failed to start: %s", exc)

    async def send_alert(
        self, tenant_id: str, alert: dict[str, Any]
    ) -> None:
        if not self._connected:
            return
        try:
            event = {
                "event_type": "opportunity.alert",
                "tenant_id": tenant_id,
                "alert_id": alert.get("alert_id", ""),
                "trend_slug": alert.get("trend_slug", ""),
                "relevance_score": alert.get("relevance_score", 0),
                "urgency": alert.get("urgency", "this_month"),
                "recommendation": alert.get("recommendation", ""),
                "affected_personas": alert.get("affected_personas", []),
                "expiry_estimate": alert.get("expiry_estimate", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await self._producer.send_and_wait(self.TOPIC, event)
        except Exception as exc:
            logger.warning("AlertProducer send failed: %s", exc)

    async def stop(self) -> None:
        if self._producer and self._connected:
            await self._producer.stop()
            self._connected = False
