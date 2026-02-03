"""
Domain Models for RAG Index Service.

Defines the core data structures used throughout the service:
- SyncEvent: Input event from rag-sync-ready-topic
- SyncResult: Result of a sync operation
- SyncStatusRecord: Status tracking record in Redis
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class SyncAction(str, Enum):
    """Document sync action types.

    UPSERT: Insert or update document in Vertex AI Search
    DELETE: Remove document from Vertex AI Search
    """

    UPSERT = "UPSERT"
    DELETE = "DELETE"


class SyncEvent(BaseModel):
    """Input event from rag-sync-ready-topic.

    Represents a document synchronization request received from
    the media-curation-svc via Kafka.

    Attributes:
        event_id: Unique identifier for this sync event
        trace_id: Distributed tracing ID for request correlation
        tenant_id: Tenant identifier for multi-tenancy
        file_id: Unique file/document identifier
        processed_gcs_uri: GCS URI of the curated JSON document
        action: Type of sync action (UPSERT or DELETE)
        timestamp: When the event was created
        metadata: Additional metadata for the event
    """

    event_id: UUID = Field(default_factory=uuid4)
    trace_id: str
    tenant_id: str
    file_id: str
    processed_gcs_uri: str = ""
    action: SyncAction
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False, "extra": "allow"}

    @field_validator("processed_gcs_uri")
    @classmethod
    def validate_gcs_uri(cls, v: str, info) -> str:
        """Validate GCS URI format for UPSERT actions."""
        # For DELETE actions, GCS URI can be empty
        if not v:
            return v
        if not v.startswith("gs://"):
            raise ValueError("GCS URI must start with 'gs://'")
        return v

    @property
    def document_id(self) -> str:
        """Alias for file_id for clarity in Vertex AI context."""
        return self.file_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": str(self.event_id),
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "file_id": self.file_id,
            "processed_gcs_uri": self.processed_gcs_uri,
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncEvent":
        """Create from dictionary."""
        return cls(
            event_id=UUID(data["event_id"])
            if isinstance(data.get("event_id"), str)
            else data.get("event_id", uuid4()),
            trace_id=data["trace_id"],
            tenant_id=data["tenant_id"],
            file_id=data["file_id"],
            processed_gcs_uri=data.get("processed_gcs_uri", ""),
            action=SyncAction(data["action"]),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data.get("timestamp"), str)
            else data.get("timestamp", datetime.now(timezone.utc)),
            metadata=data.get("metadata", {}),
        )


class SyncResult(BaseModel):
    """Result of a sync operation.

    Returned after processing a SyncEvent, containing the outcome
    and any relevant metadata.

    Attributes:
        event_id: The event that was processed
        trace_id: Distributed tracing ID
        status: Processing outcome (COMPLETED, FAILED, PENDING)
        operation_id: Vertex AI LRO operation ID (for UPSERT)
        error_message: Error details if status is FAILED
        processing_time_ms: Time taken to process in milliseconds
    """

    event_id: UUID
    trace_id: str
    status: Literal["COMPLETED", "FAILED", "PENDING"]
    operation_id: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: int = 0

    model_config = {"frozen": False}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": str(self.event_id),
            "trace_id": self.trace_id,
            "status": self.status,
            "operation_id": self.operation_id,
            "error_message": self.error_message,
            "processing_time_ms": self.processing_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncResult":
        """Create from dictionary."""
        return cls(
            event_id=UUID(data["event_id"])
            if isinstance(data.get("event_id"), str)
            else data["event_id"],
            trace_id=data["trace_id"],
            status=data["status"],
            operation_id=data.get("operation_id"),
            error_message=data.get("error_message"),
            processing_time_ms=data.get("processing_time_ms", 0),
        )


class SyncStatus(str, Enum):
    """Sync status enumeration.

    Tracks the processing state of a sync event.
    """

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SyncStatusRecord(BaseModel):
    """Status tracking record stored in Redis.

    Tracks the current processing state of a sync event,
    enabling status queries and retry logic.

    Attributes:
        event_id: The event being tracked
        trace_id: Distributed tracing ID
        tenant_id: Tenant identifier
        file_id: File identifier
        action: The sync action type
        status: Current status (PENDING, IN_PROGRESS, COMPLETED, FAILED)
        last_updated: When the status was last updated
        error_message: Error details if failed
        retry_count: Number of retry attempts
    """

    event_id: UUID
    trace_id: str
    tenant_id: str
    file_id: str
    action: SyncAction
    status: SyncStatus
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None
    retry_count: int = 0

    model_config = {"frozen": False}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return {
            "event_id": str(self.event_id),
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "file_id": self.file_id,
            "action": self.action.value,
            "status": self.status.value,
            "last_updated": self.last_updated.isoformat(),
            "error_message": self.error_message,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncStatusRecord":
        """Create from dictionary."""
        return cls(
            event_id=UUID(data["event_id"])
            if isinstance(data.get("event_id"), str)
            else data["event_id"],
            trace_id=data["trace_id"],
            tenant_id=data["tenant_id"],
            file_id=data["file_id"],
            action=SyncAction(data["action"])
            if isinstance(data.get("action"), str)
            else data["action"],
            status=SyncStatus(data["status"])
            if isinstance(data.get("status"), str)
            else data["status"],
            last_updated=datetime.fromisoformat(data["last_updated"])
            if isinstance(data.get("last_updated"), str)
            else data.get("last_updated", datetime.now(timezone.utc)),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
        )


class RateLimitStatus(BaseModel):
    """Rate limit status information.

    Used for monitoring and reporting rate limit usage.
    """

    current_count: int = 0
    limit: int = 600
    window_seconds: int = 60
    remaining: int = 600
    reset_at: Optional[datetime] = None

    @property
    def is_limited(self) -> bool:
        """Check if currently rate limited."""
        return self.current_count >= self.limit

    @property
    def available(self) -> int:
        """Number of requests available."""
        return max(0, self.limit - self.current_count)
