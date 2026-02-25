"""Async Kafka producers for trace events and social audit trail."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.messaging.schemas import SocialAuditEvent, TraceEvent

logger = logging.getLogger(__name__)

_TRACE_TOPIC = "agent-trace-topic"


class TraceProducer:
    """Emits step-level trace events for the ThoughtTrace UI."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._servers = bootstrap_servers
        self._producer: Any = None

    async def _ensure_producer(self) -> Any | None:
        if not self._servers:
            return None
        if self._producer is None:
            try:
                from aiokafka import AIOKafkaProducer

                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )
                await self._producer.start()
            except Exception as exc:
                logger.warning("Kafka TraceProducer init failed: %s", exc)
                self._producer = None
        return self._producer

    async def send_step(
        self,
        job_id: str,
        message: str,
        metadata: dict[str, Any] | None = None,
        node_id: str = "social_promoter",
        status: str = "PROCESSING",
    ) -> None:
        """Emit a trace event."""
        producer = await self._ensure_producer()
        if producer is None:
            return
        event = TraceEvent(
            job_id=job_id,
            node_id=node_id,
            status=status,
            message=message,
            metadata=metadata or {},
        )
        try:
            await producer.send_and_wait(_TRACE_TOPIC, event.model_dump())
        except Exception as exc:
            logger.warning("Failed to send trace event: %s", exc)

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None


class SocialAuditProducer:
    """Emits audit events for social media actions."""

    def __init__(self, bootstrap_servers: str, topic: str = "") -> None:
        self._servers = bootstrap_servers
        self._topic = topic or "social-audit-topic"
        self._producer: Any = None

    async def _ensure_producer(self) -> Any | None:
        if not self._servers:
            return None
        if self._producer is None:
            try:
                from aiokafka import AIOKafkaProducer

                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )
                await self._producer.start()
            except Exception as exc:
                logger.warning("Kafka SocialAuditProducer init failed: %s", exc)
                self._producer = None
        return self._producer

    async def send_audit(
        self,
        tenant_id: str,
        job_id: str,
        platform: str,
        action: str,
        content_preview: str = "",
        user_role: str = "",
    ) -> None:
        """Emit a social audit event."""
        producer = await self._ensure_producer()
        if producer is None:
            return
        event = SocialAuditEvent(
            tenant_id=tenant_id,
            job_id=job_id,
            platform=platform,
            action=action,
            content_preview=content_preview[:200],
            user_role=user_role,
        )
        try:
            await producer.send_and_wait(self._topic, event.model_dump())
        except Exception as exc:
            logger.warning("Failed to send audit event: %s", exc)

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
