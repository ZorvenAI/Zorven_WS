"""Kafka producers for the Voice of Customer Agent.

Three producers:
- TraceProducer → agent-trace-topic (real-time node progress)
- AuditProducer → voc-audit-topic (audit trail)
- AlertProducer → voc-insights-topic (VoC insight alerts)
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
            "node_id": "voice_of_customer",
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

    async def send_step(
        self, job_id: str, step: str, status: str = "running"
    ) -> None:
        await self.send_trace(
            job_id, status, message=f"VoCA: {step}"
        )


class AuditProducer:
    """Emits audit trail events to voc-audit-topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer = None
        self._topic = "voc-audit-topic"

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


class AlertProducer:
    """Emits VoC insight alerts to voc-insights-topic."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap = bootstrap_servers
        self._producer = None
        self._topic = "voc-insights-topic"

    async def start(self) -> None:
        if not self._bootstrap:
            logger.info("AlertProducer in stub mode (no bootstrap servers)")
            return
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
            await self._producer.start()
            logger.info("AlertProducer started: %s", self._topic)
        except Exception as exc:
            logger.warning("AlertProducer start failed: %s", exc)
            self._producer = None

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send_alert(
        self,
        tenant_id: str,
        alert_id: str,
        alert_type: str,
        severity: str,
        title: str,
        description: str = "",
        affected_personas: list[str] | None = None,
        recommendation: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "tenant_id": tenant_id,
            "alert_id": alert_id,
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "description": description,
            "affected_personas": affected_personas or [],
            "recommendation": recommendation,
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if self._producer:
            try:
                await self._producer.send_and_wait(self._topic, payload)
            except Exception as exc:
                logger.warning("Alert send failed: %s", exc)
        else:
            logger.debug("Alert (stub): %s", payload)
