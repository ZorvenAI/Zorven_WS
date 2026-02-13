"""
NoOp Producer Adapter for Media Curation.

A no-operation implementation of the EventProducerPort that silently
succeeds without publishing to Kafka. Used when Kafka is disabled
and pipeline stages are chained directly via Celery.
"""

import logging
from typing import Any, Optional

from media_curation.domain.models import CurationEvent, CuratedDocument
from media_curation.ports.event_port import EventProducerPort


logger = logging.getLogger(__name__)


class NoOpProducerAdapter(EventProducerPort):
    """
    No-operation Kafka producer for the curation pipeline.

    All publish methods log and return successfully without
    actually sending messages. The CurationService can complete
    its full processing when Kafka is unavailable.
    """

    async def publish_curated_document(
        self,
        topic: str,
        document: CuratedDocument,
        key: Optional[str] = None,
    ) -> None:
        """Log and skip curated document publish."""
        logger.info(
            "NoOp producer: skipping curated doc publish to %s (doc_id=%s)",
            topic,
            document.document_id,
        )

    async def publish_to_dlq(
        self,
        event: CurationEvent,
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """Log and skip DLQ publish."""
        logger.warning(
            "NoOp producer: would send curation event to DLQ: %s",
            error,
        )

    async def publish_raw(
        self,
        topic: str,
        payload: dict[str, Any],
        key: Optional[str] = None,
    ) -> None:
        """Log and skip raw publish."""
        logger.info(
            "NoOp producer: skipping raw publish to %s",
            topic,
        )

    def flush(self, timeout: float = 10.0) -> int:
        """No-op flush — always returns 0 (no pending messages)."""
        return 0
