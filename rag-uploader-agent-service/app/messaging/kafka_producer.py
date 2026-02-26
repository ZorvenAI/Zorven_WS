"""
Kafka producers for rag-uploader-agent-svc.

TraceProducer       — emits step updates to agent-trace-topic
IngestionProducer   — emits ingestion events to raw-ingestion-topic

Both degrade gracefully when Kafka is unavailable.
"""

import json
import logging
from typing import Any, Optional

from app.messaging.schemas import IngestionEventSchema, TraceEvent

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
        node_id: str = "rag_uploader",
        status: str = "PROCESSING",
    ) -> None:
        """Emit a trace step event.

        Gracefully no-ops when Kafka is unavailable.
        """
        event = TraceEvent(
            job_id=job_id,
            node_id=node_id,
            status=status,
            message=message,
            metadata=metadata or {},
            output={"last_thought": message},
        )

        if self._producer is None:
            logger.debug("TraceProducer not connected, skipping: %s", message)
            return

        try:
            await self._producer.send_and_wait(self.TOPIC, event.model_dump())
            logger.debug("Trace event sent: %s", message)
        except Exception as exc:
            logger.warning("Failed to send trace event: %s", exc)


class IngestionProducer:
    """Emits ingestion events to raw-ingestion-topic.

    Triggers the existing Data Ingestion → Curation → Vertex AI Indexing
    pipeline by producing messages that match the IngestionEvent schema.
    """

    TOPIC = "raw-ingestion-topic"

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
            logger.info("Kafka disabled — IngestionProducer in no-op mode")
            return

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info("IngestionProducer connected to %s", self.bootstrap_servers)
        except Exception as exc:
            logger.warning(
                "IngestionProducer failed to connect: %s. Running in no-op mode.",
                exc,
            )

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping IngestionProducer: %s", exc)
            self._producer = None
            self._connected = False

    async def send_ingestion_event(self, event: dict[str, Any], tenant_id: str) -> bool:
        """Emit an ingestion event to raw-ingestion-topic.

        Returns True on success, False on failure.
        Gracefully no-ops when Kafka is unavailable.
        """
        if self._producer is None:
            logger.debug(
                "IngestionProducer not connected, skipping event for %s",
                tenant_id,
            )
            return False

        try:
            headers = [
                ("trace_id", str(event.get("trace_id", "")).encode("utf-8")),
                ("event_type", b"ingestion_event"),
            ]
            await self._producer.send_and_wait(
                self.TOPIC,
                event,
                key=tenant_id.encode("utf-8"),
                headers=headers,
            )
            logger.debug(
                "Ingestion event sent for tenant %s: %s",
                tenant_id,
                event.get("event_id", ""),
            )
            return True
        except Exception as exc:
            logger.warning("Failed to send ingestion event: %s", exc)
            return False
