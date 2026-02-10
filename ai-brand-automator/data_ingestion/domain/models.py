"""
Domain Models for Data Ingestion Pipeline.

Pure Pydantic models with no external dependencies.
These models define the data structures for events flowing through the pipeline.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class EventSource(str, Enum):
    """Source system that generated the ingestion event."""

    KONG_GATEWAY = "kong-gateway"
    DJANGO_BACKEND = "django-backend"
    FRONTEND_UPLOAD = "frontend-upload"
    API_INTEGRATION = "api-integration"
    BATCH_IMPORT = "batch-import"


class FileType(str, Enum):
    """Supported file types for ingestion."""

    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    """Status of event processing in the pipeline."""

    PENDING = "pending"
    VALIDATING = "validating"
    MOVING = "moving"
    RAW_STORED = "raw_stored"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class IngestionEvent(BaseModel):
    """
    Event model for incoming data ingestion requests.

    This is the primary input to the ingestion pipeline, received from Kafka.
    """

    event_id: UUID = Field(
        description="Unique identifier for this event (used for deduplication)"
    )
    trace_id: UUID = Field(
        description="Trace ID for distributed tracing across services"
    )
    timestamp: datetime = Field(description="When the event was created")
    source: EventSource = Field(description="System that generated this event")
    tenant_id: str = Field(
        min_length=1,
        max_length=100,
        description="Tenant identifier (e.g., 'customer-1')",
    )
    file_path: str = Field(
        min_length=1,
        description="Full GCS path to the file (e.g., 'gs://bucket/_landing/file.mp4')",
    )
    file_type: str = Field(description="MIME type of the file (e.g., 'video/mp4')")
    file_size_bytes: Optional[int] = Field(
        default=None, ge=0, description="Size of the file in bytes"
    )
    metadata: Optional[dict] = Field(
        default_factory=dict, description="Additional metadata about the file"
    )
    raw_bucket: Optional[str] = Field(
        default=None,
        description="Per-tenant raw bucket override (from tenant.get_raw_bucket())",
    )
    curated_bucket: Optional[str] = Field(
        default=None,
        description="Per-tenant curated bucket override (from tenant.get_curated_bucket())",
    )

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        """Validate tenant_id contains only safe characters."""
        # Allow alphanumeric, hyphens, underscores
        import re

        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "tenant_id must contain only alphanumeric characters, "
                "hyphens, and underscores"
            )
        return v.lower()  # Normalize to lowercase

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        """Validate file_path is a valid GCS path."""
        if not v.startswith("gs://"):
            raise ValueError("file_path must be a GCS URI starting with 'gs://'")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_id": "550e8400-e29b-41d4-a716-446655440000",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440001",
                    "timestamp": "2026-01-29T10:00:00Z",
                    "source": "frontend-upload",
                    "tenant_id": "customer-1",
                    "file_path": "gs://onboarding-bucket1/_landing/video.mp4",
                    "file_type": "video/mp4",
                    "file_size_bytes": 1048576,
                    "metadata": {"original_name": "product_demo.mp4"},
                }
            ]
        }
    }


class FileMetadata(BaseModel):
    """
    Metadata about a file in GCS.

    Returned from storage operations to provide file information.
    """

    bucket: str = Field(description="GCS bucket name")
    path: str = Field(description="Path within the bucket (without gs:// prefix)")
    full_uri: str = Field(description="Full GCS URI (gs://bucket/path)")
    size_bytes: int = Field(ge=0, description="File size in bytes")
    content_type: str = Field(description="MIME type of the file")
    created_at: datetime = Field(description="When the file was created/uploaded")
    updated_at: Optional[datetime] = Field(
        default=None, description="When the file was last modified"
    )
    md5_hash: Optional[str] = Field(
        default=None, description="MD5 hash of file contents"
    )
    etag: Optional[str] = Field(default=None, description="GCS ETag")

    @classmethod
    def from_gcs_blob(cls, blob) -> "FileMetadata":
        """
        Create FileMetadata from a google.cloud.storage.Blob object.

        Args:
            blob: GCS Blob object

        Returns:
            FileMetadata instance
        """
        return cls(
            bucket=blob.bucket.name,
            path=blob.name,
            full_uri=f"gs://{blob.bucket.name}/{blob.name}",
            size_bytes=blob.size or 0,
            content_type=blob.content_type or "application/octet-stream",
            created_at=blob.time_created or datetime.utcnow(),
            updated_at=blob.updated,
            md5_hash=blob.md5_hash,
            etag=blob.etag,
        )


class ProcessedEvent(BaseModel):
    """
    Output event after successful ingestion processing.

    Published to the output Kafka topic for downstream services.
    """

    event_id: UUID = Field(description="Original event ID")
    trace_id: UUID = Field(description="Trace ID for distributed tracing")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When processing completed"
    )
    tenant_id: str = Field(description="Tenant identifier")
    source_path: str = Field(description="Original landing zone path")
    destination_path: str = Field(description="New raw storage path")
    status: ProcessingStatus = Field(
        default=ProcessingStatus.RAW_STORED, description="Processing status"
    )
    file_metadata: Optional[FileMetadata] = Field(
        default=None, description="Metadata about the processed file"
    )
    processing_duration_ms: Optional[int] = Field(
        default=None, ge=0, description="Time taken to process in milliseconds"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if processing failed"
    )
    metadata: Optional[dict] = Field(
        default_factory=dict, description="Original event metadata (includes asset_id)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_id": "550e8400-e29b-41d4-a716-446655440000",
                    "trace_id": "550e8400-e29b-41d4-a716-446655440001",
                    "timestamp": "2026-01-29T10:00:05Z",
                    "tenant_id": "customer-1",
                    "source_path": "gs://onboarding-bucket1/_landing/video.mp4",
                    "destination_path": "gs://onboarding-bucket1/customer-1/raw/2026/01/29/video.mp4",
                    "status": "raw_stored",
                    "processing_duration_ms": 1250,
                }
            ]
        }
    }
