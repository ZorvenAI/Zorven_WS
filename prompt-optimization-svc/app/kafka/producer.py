"""Kafka producers for trace and audit events."""

import json
import logging
from typing import Any, Optional

from app.kafka.schemas import AuditEvent, PromptLifecycleEvent, TraceEvent

logger = logging.getLogger(__name__)


class TraceProducer:
    """Emits trace events to agent-trace-topic for ThoughtTrace UI."""

    TOPIC = "agent-trace-topic"

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the Kafka producer."""
        if not self.bootstrap_servers:
            logger.info("Kafka disabled — TraceProducer in no-op mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await producer.start()
            self._producer = producer
            self._connected = True
            logger.info("TraceProducer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            self._producer = None
            logger.warning("TraceProducer failed: %s — no-op mode", exc)

    async def stop(self) -> None:
        """Stop the producer."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping TraceProducer: %s", exc)
            self._producer = None
            self._connected = False

    async def send_step(
        self,
        job_id: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
        node_id: str = "prompt_optimization_worker",
        status: str = "PROCESSING",
    ) -> None:
        """Emit a trace step event."""
        if self._producer is None:
            return
        event = TraceEvent(
            job_id=job_id,
            node_id=node_id,
            status=status,
            message=message,
            metadata=metadata or {},
        )
        try:
            await self._producer.send_and_wait(self.TOPIC, event.model_dump())
        except Exception as exc:
            logger.warning("Failed to send trace event: %s", exc)


class AuditProducer:
    """Emits audit events to poi-optimization-audit-topic."""

    TOPIC = "poi-optimization-audit-topic"

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the Kafka producer."""
        if not self.bootstrap_servers:
            logger.info("Kafka disabled — AuditProducer in no-op mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await producer.start()
            self._producer = producer
            self._connected = True
            logger.info("AuditProducer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            self._producer = None
            logger.warning("AuditProducer failed: %s — no-op mode", exc)

    async def stop(self) -> None:
        """Stop the producer."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping AuditProducer: %s", exc)
            self._producer = None
            self._connected = False

    async def send_audit(
        self,
        job_id: str,
        tenant_id: str,
        action: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Emit an audit event."""
        if self._producer is None:
            return
        event = AuditEvent(
            job_id=job_id,
            tenant_id=tenant_id,
            action=action,
            details=details or {},
        )
        try:
            await self._producer.send_and_wait(self.TOPIC, event.model_dump())
        except Exception as exc:
            logger.warning("Failed to send audit event: %s", exc)


class LifecycleProducer:
    """Emits prompt lifecycle events to prompt-lifecycle-events topic (AC-6)."""

    TOPIC = "prompt-lifecycle-events"

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer: Any = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the Kafka producer."""
        if not self.bootstrap_servers:
            logger.info("Kafka disabled — LifecycleProducer in no-op mode")
            return
        try:
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await producer.start()
            self._producer = producer
            self._connected = True
            logger.info("LifecycleProducer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            self._producer = None
            logger.warning("LifecycleProducer failed: %s — no-op mode", exc)

    async def stop(self) -> None:
        """Stop the producer."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping LifecycleProducer: %s", exc)
            self._producer = None
            self._connected = False

    def send_lifecycle_event_sync(
        self,
        event_type: str,
        prompt_name: str,
        version: int,
        from_state: str,
        to_state: str,
        tenant_id: Optional[str] = None,
        agent_code: str = "",
        correlation_id: Optional[str] = None,
    ) -> None:
        """Emit a lifecycle event (fire-and-forget, sync wrapper).

        Args:
            event_type: Event type constant (e.g., PROMPT_PROMOTED).
            prompt_name: Affected prompt name.
            version: Prompt version.
            from_state: Previous state.
            to_state: New state.
            tenant_id: Tenant ID (optional).
            agent_code: Agent code for routing.
            correlation_id: Unique ID for dedup (AC-4). Auto-generated if None.
        """
        if self._producer is None:
            logger.debug("LifecycleProducer not connected, skipping: %s", event_type)
            return

        from app.kafka.schemas import SCHEMA_VERSION

        event = PromptLifecycleEvent(
            event_type=event_type,
            prompt_name=prompt_name,
            version=version,
            from_state=from_state,
            to_state=to_state,
            tenant_id=tenant_id,
            agent_code=agent_code,
            **({"correlation_id": correlation_id} if correlation_id else {}),
        )

        # Use correlation_id as message key for idempotent dedup (AC-4)
        message_key = event.correlation_id.encode("utf-8")
        headers = [("schema_version", SCHEMA_VERSION.encode("utf-8"))]

        try:
            import asyncio

            loop = asyncio.get_event_loop()
            coro = self._producer.send_and_wait(
                self.TOPIC,
                event.model_dump(),
                key=message_key,
                headers=headers,
            )
            if loop.is_running():
                loop.create_task(coro)
            else:
                loop.run_until_complete(coro)
        except Exception as exc:
            logger.warning("Failed to send lifecycle event: %s", exc)
