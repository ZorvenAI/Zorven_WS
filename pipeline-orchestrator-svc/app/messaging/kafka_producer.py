"""
Kafka trace producer — emits real-time trace events for pipeline execution.

Publishes to:
  - agent-trace-topic: Per-node status events (started, completed, failed)
  - pipeline-result-topic: Final pipeline result data
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_producer = None


class TraceProducer:
    """Kafka producer for pipeline trace and result events."""

    def __init__(self, bootstrap_servers: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self._producer = None

    async def start(self) -> None:
        """Start the Kafka producer."""
        try:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()
            logger.info(
                "Kafka trace producer started: %s",
                self.bootstrap_servers,
            )
        except Exception as exc:
            logger.warning(
                "Kafka producer failed to start (running HTTP-only): %s",
                exc,
            )
            self._producer = None

    async def stop(self) -> None:
        """Stop the Kafka producer."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka trace producer stopped")

    async def send_trace(
        self,
        job_id: str,
        node_id: str,
        status: str,
        output: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Emit a per-node trace event to agent-trace-topic.

        Non-fatal if Kafka is unavailable.
        """
        if self._producer is None:
            return

        event = {
            "job_id": job_id,
            "node_id": node_id,
            "status": status,
            "output": output,
        }

        try:
            await self._producer.send_and_wait(
                "agent-trace-topic",
                value=event,
                key=job_id.encode("utf-8"),
            )
        except Exception as exc:
            logger.warning(
                "Failed to send trace event for job %s node %s: %s",
                job_id,
                node_id,
                exc,
            )

    async def send_result(
        self,
        job_id: str,
        result_data: dict[str, Any],
    ) -> None:
        """
        Emit final pipeline result to pipeline-result-topic.

        Non-fatal if Kafka is unavailable.
        """
        if self._producer is None:
            return

        event = {
            "job_id": job_id,
            "result_data": result_data,
        }

        try:
            await self._producer.send_and_wait(
                "pipeline-result-topic",
                value=event,
                key=job_id.encode("utf-8"),
            )
        except Exception as exc:
            logger.warning(
                "Failed to send result event for job %s: %s",
                job_id,
                exc,
            )

    @property
    def is_connected(self) -> bool:
        """Check if the producer is connected."""
        return self._producer is not None
