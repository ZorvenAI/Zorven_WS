"""
NoOp Producer Adapter.

A no-operation implementation of the EventProducerPort that silently
succeeds without publishing to Kafka. Used when Kafka is disabled
and pipeline stages are chained directly via Celery.
"""

import logging
from typing import Optional

from data_ingestion.domain.models import ProcessedEvent
from data_ingestion.ports.event_port import EventProducerPort


logger = logging.getLogger(__name__)


class NoOpProducerAdapter(EventProducerPort):
    """
    No-operation Kafka producer.

    All publish methods log and return successfully without
    actually sending messages. This allows the IngestionService
    to complete its full processing pipeline (steps 1-8) when
    Kafka is unavailable, with inter-stage handoff handled
    externally (e.g., by a Celery orchestration task).
    """

    def publish(
        self,
        topic: str,
        event: ProcessedEvent,
        key: Optional[str] = None,
    ) -> None:
        """Log and skip Kafka publish."""
        logger.info(
            "NoOp producer: skipping publish to %s (event_id=%s)",
            topic,
            event.event_id,
        )

    def publish_raw(
        self,
        topic: str,
        payload: dict,
        key: Optional[str] = None,
    ) -> None:
        """Log and skip raw publish."""
        logger.info(
            "NoOp producer: skipping raw publish to %s",
            topic,
        )

    def publish_to_dlq(
        self,
        original_event: dict,
        error: Exception,
        source_topic: str,
    ) -> None:
        """Log and skip DLQ publish."""
        logger.warning(
            "NoOp producer: would send to DLQ from %s: %s",
            source_topic,
            error,
        )

    def flush(self, timeout_seconds: float = 10.0) -> int:
        """No-op flush — always returns 0 (no pending messages)."""
        return 0
