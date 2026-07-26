"""
CloudEvents Wire Format Schemas.

These schemas define the JSON structure for events
exchanged over Kafka topics following CloudEvents spec.
"""

from datetime import datetime, timezone
from typing import Optional, Any

from pydantic import BaseModel, Field


class CloudEventBase(BaseModel):
    """
    CloudEvents specification base schema.

    Reference: https://cloudevents.io/
    """

    specversion: str = "1.0"
    id: str  # Unique event ID
    type: str  # Event type identifier
    source: str  # Event source URI
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    datacontenttype: str = "application/json"
    subject: Optional[str] = None  # Event subject
    traceid: Optional[str] = None  # Trace ID for distributed tracing
    data: dict[str, Any] = Field(default_factory=dict)


class CurationNeededEvent(CloudEventBase):
    """
    Event schema for curation-needed-topic.

    Produced by: data_ingestion service
    Consumed by: media_curation service

    Data payload should contain:
    - trace_id: UUID (string)
    - tenant_id: UUID (string)
    - file_id: UUID (string)
    - raw_gcs_uri: GCS URI
    - mime_type: MIME type
    - metadata: optional dict
    """

    type: str = "zorven.ingestion.completed.v1"
    source: str = "data-ingestion-svc"


class CurationCompletedEvent(CloudEventBase):
    """
    Event schema for rag-sync-ready-topic.

    Produced by: media_curation service
    Consumed by: rag-indexer service

    Data payload should contain:
    - trace_id: UUID (string)
    - tenant_id: UUID (string)
    - file_id: UUID (string)
    - document_id: UUID (string)
    - curated_gcs_uri: GCS URI
    - mime_type: MIME type
    - pii_redacted: bool
    """

    type: str = "zorven.curation.completed.v1"
    source: str = "media-curation-svc"


class CurationFailedEvent(CloudEventBase):
    """
    Event schema for curation-dlq (dead letter queue).

    Contains failed events with error details for retry/investigation.

    Data payload should contain:
    - trace_id: UUID (string)
    - tenant_id: UUID (string)
    - file_id: UUID (string)
    - raw_gcs_uri: GCS URI
    - mime_type: MIME type
    - error_code: Error class name
    - error_message: Error description
    - retry_count: Number of retries
    """

    type: str = "zorven.curation.failed.v1"
    source: str = "media-curation-svc"
