"""Pydantic models for Kafka events produced by this service."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Trace event for the ThoughtTrace UI (agent-trace-topic)."""

    job_id: str = ""
    node_id: str = "rag_uploader"
    status: str = "PROCESSING"
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)


class IngestionEventSchema(BaseModel):
    """Mirrors the IngestionEvent schema from data_ingestion domain.

    Sent to the raw-ingestion-topic Kafka topic to trigger the
    existing Data Ingestion → Curation → Vertex AI Indexing pipeline.
    """

    event_id: str = Field(description="UUID string for deduplication")
    trace_id: str = Field(description="UUID string for distributed tracing")
    timestamp: str = Field(description="ISO 8601 datetime")
    source: str = Field(
        default="api-integration",
        description="EventSource enum value from data_ingestion domain",
    )
    tenant_id: str = Field(description="Tenant identifier")
    file_path: str = Field(description="Full GCS URI (gs://bucket/path)")
    file_type: str = Field(description="MIME type of the file")
    file_size_bytes: Optional[int] = Field(
        default=None, description="File size in bytes"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (custom_title, original_name, etc.)",
    )
