"""Bridges to the existing Data Ingestion Pipeline via Kafka.

Formats payloads to match the IngestionEvent schema expected by
data-ingestion-svc and emits them to the raw-ingestion-topic.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.messaging.kafka_producer import IngestionProducer
from app.messaging.schemas import IngestionEventSchema

logger = logging.getLogger(__name__)


class IngestionBridge:
    """Emits IngestionEvent messages to trigger the ingestion pipeline."""

    def __init__(self, ingestion_producer: IngestionProducer) -> None:
        self._producer = ingestion_producer

    async def emit(
        self,
        file_path: str,
        file_type: str,
        file_size_bytes: int,
        tenant_id: str,
        metadata: dict[str, Any],
        trace_id: str = "",
    ) -> bool:
        """Build and emit an IngestionEvent to raw-ingestion-topic.

        Args:
            file_path: Full GCS URI (gs://bucket/path/file.ext).
            file_type: MIME type of the file.
            file_size_bytes: Size of the file in bytes.
            tenant_id: Tenant identifier.
            metadata: Additional metadata (custom_title, original_name, etc.).
            trace_id: Optional trace ID for distributed tracing.

        Returns:
            True if the event was emitted, False otherwise.
        """
        event = IngestionEventSchema(
            event_id=str(uuid4()),
            trace_id=trace_id or str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="api-integration",
            tenant_id=tenant_id,
            file_path=file_path,
            file_type=file_type,
            file_size_bytes=file_size_bytes if file_size_bytes > 0 else None,
            metadata=metadata,
        )

        success = await self._producer.send_ingestion_event(
            event.model_dump(), tenant_id
        )

        if success:
            logger.info(
                "Ingestion event emitted: tenant=%s file=%s event_id=%s",
                tenant_id,
                file_path,
                event.event_id,
            )
        else:
            logger.warning(
                "Failed to emit ingestion event: tenant=%s file=%s",
                tenant_id,
                file_path,
            )

        return success
