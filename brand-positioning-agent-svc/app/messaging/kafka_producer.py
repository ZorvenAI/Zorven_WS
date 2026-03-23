"""Kafka producers for the Brand Positioning Agent.

Three producers:
- TraceProducer → agent-trace-topic (real-time node progress)
- AuditProducer → bpa-positioning-audit-topic (audit trail)
- EventProducer → bpa-positioning-events-topic (positioning events)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class TraceProducer:
    """Emits real-time node progress to agent-trace-topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer = None
        self._topic = "agent-trace-topic"

    async def start(self) -> None:
        if not self._bootstrap:
            logger.info("TraceProducer in stub mode (no bootstrap servers)")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()
            logger.info("TraceProducer started: %s", self._topic)
        except Exception as exc:
            logger.warning("TraceProducer start failed: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send_trace(
        self,
        job_id: str,
        status: str,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "job_id": job_id,
            "node_id": "brand_positioning",
            "status": status,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self._producer:
            try:
                await self._producer.send_and_wait(self._topic, payload)
            except Exception as exc:
                logger.warning("Trace send failed: %s", exc)
        else:
            logger.debug("Trace (stub): %s", payload)

    async def send_step(self, job_id: str, step: str, status: str = "running") -> None:
        await self.send_trace(job_id, status, message=f"BPA: {step}")


class AuditProducer:
    """Emits audit trail events to bpa-positioning-audit-topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer = None
        self._topic = "bpa-positioning-audit-topic"

    async def start(self) -> None:
        if not self._bootstrap:
            logger.info("AuditProducer in stub mode (no bootstrap servers)")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()
            logger.info("AuditProducer started: %s", self._topic)
        except Exception as exc:
            logger.warning("AuditProducer start failed: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send_event(
        self,
        event_type: str,
        event_name: str,
        tenant_id: str = "",
        session_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "event_type": event_type,
            "event_name": event_name,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self._producer:
            try:
                await self._producer.send_and_wait(self._topic, payload)
            except Exception as exc:
                logger.warning("Audit send failed: %s", exc)
        else:
            logger.debug("Audit (stub): %s", payload)


class EventProducer:
    """Emits positioning strategy events to bpa-positioning-events-topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer = None
        self._topic = "bpa-positioning-events-topic"

    async def start(self) -> None:
        if not self._bootstrap:
            logger.info("EventProducer in stub mode (no bootstrap servers)")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()
            logger.info("EventProducer started: %s", self._topic)
        except Exception as exc:
            logger.warning("EventProducer start failed: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send_event(
        self,
        tenant_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self._producer:
            try:
                await self._producer.send_and_wait(self._topic, payload)
            except Exception as exc:
                logger.warning("Event send failed: %s", exc)
        else:
            logger.debug("Event (stub): %s", payload)
