"""
CloudEvents Schema Definitions for RAG Index Service.

Defines the CloudEvents-compliant schema for sync events
published to and consumed from Kafka topics.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .models import SyncAction, SyncResult


class CloudEventBase(BaseModel):
    """Base CloudEvents v1.0 schema.

    All events in the system conform to the CloudEvents specification.
    https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
    """

    specversion: str = "1.0"
    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    type: str
    time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    datacontenttype: str = "application/json"
    subject: Optional[str] = None

    model_config = {"extra": "allow"}


class RagSyncReadyEventData(BaseModel):
    """Data payload for rag-sync-ready-topic events.

    This is the payload received from media-curation-svc.
    """

    tenant_id: str
    file_id: str
    processed_gcs_uri: str = ""
    action: SyncAction
    trace_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagSyncReadyEvent(CloudEventBase):
    """CloudEvents schema for rag-sync-ready-topic.

    Consumed from media-curation-svc when a document is ready
    for syncing to Vertex AI Search.
    """

    type: str = "com.prevision.rag.sync.ready"
    source: str = "/media-curation-svc"
    data: RagSyncReadyEventData

    @classmethod
    def from_kafka_message(cls, message: dict[str, Any]) -> "RagSyncReadyEvent":
        """Parse a Kafka message into a CloudEvent."""
        return cls(**message)

    def to_sync_event(self):
        """Convert to internal SyncEvent domain model."""
        from .models import SyncEvent as SyncEventModel

        return SyncEventModel(
            event_id=UUID(self.id) if isinstance(self.id, str) else self.id,
            trace_id=self.data.trace_id,
            tenant_id=self.data.tenant_id,
            file_id=self.data.file_id,
            processed_gcs_uri=self.data.processed_gcs_uri,
            action=self.data.action,
            timestamp=datetime.fromisoformat(self.time.replace("Z", "+00:00"))
            if isinstance(self.time, str)
            else self.time,
            metadata=self.data.metadata,
        )


class RagSyncCompletedEventData(BaseModel):
    """Data payload for rag-sync-completed events."""

    event_id: str
    trace_id: str
    tenant_id: str
    file_id: str
    status: Literal["COMPLETED", "FAILED", "PENDING"]
    operation_id: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: int = 0


class RagSyncCompletedEvent(CloudEventBase):
    """CloudEvents schema for rag-sync-completed topic.

    Published after successfully syncing a document to Vertex AI Search.
    """

    type: str = "com.prevision.rag.sync.completed"
    source: str = "/rag-index-svc"
    data: RagSyncCompletedEventData

    @classmethod
    def from_sync_result(
        cls,
        result: SyncResult,
        tenant_id: str,
        file_id: str,
    ) -> "RagSyncCompletedEvent":
        """Create from a SyncResult."""
        return cls(
            id=str(result.event_id),
            subject=file_id,
            data=RagSyncCompletedEventData(
                event_id=str(result.event_id),
                trace_id=result.trace_id,
                tenant_id=tenant_id,
                file_id=file_id,
                status=result.status,
                operation_id=result.operation_id,
                error_message=result.error_message,
                processing_time_ms=result.processing_time_ms,
            ),
        )

    def to_kafka_message(self) -> dict[str, Any]:
        """Convert to Kafka message format."""
        return self.model_dump(mode="json")


class RagSyncDLQEventData(BaseModel):
    """Data payload for dead letter queue events."""

    original_event: dict[str, Any]
    error_type: str
    error_message: str
    trace_id: str
    retry_count: int = 0
    failed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class RagSyncDLQEvent(CloudEventBase):
    """CloudEvents schema for rag-sync-dlq (dead letter queue).

    Published when an event cannot be processed after max retries.
    """

    type: str = "com.prevision.rag.sync.dlq"
    source: str = "/rag-index-svc"
    data: RagSyncDLQEventData

    @classmethod
    def from_failed_event(
        cls,
        original_event: dict[str, Any],
        error: Exception,
        trace_id: str,
        retry_count: int = 0,
    ) -> "RagSyncDLQEvent":
        """Create a DLQ event from a failed processing attempt."""
        return cls(
            subject=original_event.get("data", {}).get("file_id", "unknown"),
            data=RagSyncDLQEventData(
                original_event=original_event,
                error_type=type(error).__name__,
                error_message=str(error),
                trace_id=trace_id,
                retry_count=retry_count,
            ),
        )

    def to_kafka_message(self) -> dict[str, Any]:
        """Convert to Kafka message format."""
        return self.model_dump(mode="json")
