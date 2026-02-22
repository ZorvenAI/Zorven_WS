"""
Kafka producers for intelligence-agent-svc.

TraceProducer  — emits step updates to agent-trace-topic
AuditProducer  — emits valuation audit records to valuation-audit-logs

Both degrade gracefully when Kafka is unavailable.
"""

import json
import logging
from typing import Any, Optional

from app.messaging.schemas import TraceEvent, ValuationAuditEvent

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

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info("TraceProducer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            logger.warning(
                "TraceProducer failed to connect: %s. Running in no-op mode.",
                exc,
            )

    async def stop(self) -> None:
        """Stop the Kafka producer."""
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
        node_id: str = "intelligence_worker",
        status: str = "PROCESSING",
    ) -> None:
        """
        Emit a trace step event.

        Gracefully no-ops when Kafka is unavailable.
        """
        event = TraceEvent(
            job_id=job_id,
            node_id=node_id,
            status=status,
            message=message,
            metadata=metadata or {},
        )

        if self._producer is None:
            logger.debug("TraceProducer not connected, skipping: %s", message)
            return

        try:
            await self._producer.send_and_wait(self.TOPIC, event.model_dump())
            logger.debug("Trace event sent: %s", message)
        except Exception as exc:
            logger.warning("Failed to send trace event: %s", exc)


class AuditProducer:
    """Emits valuation audit events to valuation-audit-logs for legal defensibility."""

    TOPIC = "valuation-audit-logs"

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

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info("AuditProducer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            logger.warning(
                "AuditProducer failed to connect: %s. Running in no-op mode.",
                exc,
            )

    async def stop(self) -> None:
        """Stop the Kafka producer."""
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
        methodology: str,
        royalty_rate: float,
        discount_rate: float,
        tax_rate: float,
        npv: float,
        bsi_score: int,
        data_completeness: float,
    ) -> None:
        """
        Emit a valuation audit event with math constants.

        Gracefully no-ops when Kafka is unavailable.
        """
        event = ValuationAuditEvent(
            job_id=job_id,
            tenant_id=tenant_id,
            methodology=methodology,
            royalty_rate=royalty_rate,
            discount_rate=discount_rate,
            tax_rate=tax_rate,
            npv=npv,
            bsi_score=bsi_score,
            data_completeness=data_completeness,
        )

        if self._producer is None:
            logger.debug(
                "AuditProducer not connected, skipping audit for tenant %s",
                tenant_id,
            )
            return

        try:
            await self._producer.send_and_wait(self.TOPIC, event.model_dump())
            logger.debug("Audit event sent for tenant %s", tenant_id)
        except Exception as exc:
            logger.warning("Failed to send audit event: %s", exc)
