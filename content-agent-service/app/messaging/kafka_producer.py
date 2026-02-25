"""
Kafka producers for content-agent-svc.

TraceProducer            — emits step updates to agent-trace-topic
ContentPublishedProducer — emits blog publish events to content-published-topic

Both degrade gracefully when Kafka is unavailable.
"""

import json
import logging
from typing import Any, Optional

from app.messaging.schemas import ContentPublishedEvent, TraceEvent

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
        node_id: str = "content_worker",
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


class ContentPublishedProducer:
    """Emits blog publish events to content-published-topic for downstream agents."""

    TOPIC = "content-published-topic"

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
            logger.info("Kafka disabled — ContentPublishedProducer in no-op mode")
            return

        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            self._connected = True
            logger.info(
                "ContentPublishedProducer connected to %s", self.bootstrap_servers
            )
        except Exception as exc:
            logger.warning(
                "ContentPublishedProducer failed to connect: %s. Running in no-op mode.",
                exc,
            )

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as exc:
                logger.warning("Error stopping ContentPublishedProducer: %s", exc)
            self._producer = None
            self._connected = False

    async def send_published(
        self,
        blog_id: str,
        tenant_id: str,
        gcs_uri: str,
        seo_meta: dict[str, Any],
        title: str,
    ) -> None:
        """
        Emit a content-published event.

        Gracefully no-ops when Kafka is unavailable.
        """
        event = ContentPublishedEvent(
            blog_id=blog_id,
            tenant_id=tenant_id,
            title=title,
            markdown_uri=gcs_uri,
            seo_meta=seo_meta,
        )

        if self._producer is None:
            logger.debug(
                "ContentPublishedProducer not connected, skipping publish for %s",
                blog_id,
            )
            return

        try:
            await self._producer.send_and_wait(self.TOPIC, event.model_dump())
            logger.debug("Content published event sent for blog %s", blog_id)
        except Exception as exc:
            logger.warning("Failed to send content published event: %s", exc)
