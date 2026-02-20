"""Kafka event schemas for discovery-agent-svc."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """
    Trace event for agent-trace-topic.

    Emitted at each step of the discovery process for
    real-time UI updates via ThoughtTrace.
    """

    job_id: str = Field(..., description="Pipeline job ID")
    node_id: str = Field(
        default="discovery_worker", description="Node ID in the pipeline"
    )
    status: str = Field(
        default="PROCESSING", description="Event status (PROCESSING, COMPLETE, ERROR)"
    )
    message: str = Field(..., description="Human-readable step description")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )


class AuditEvent(BaseModel):
    """
    Audit event for discovery-audit-topic.

    Stores raw HTML vs cleaned Markdown for compliance auditing.
    """

    job_id: str = Field(..., description="Pipeline job ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    url: str = Field(..., description="Source URL that was scraped")
    raw_html: str = Field(..., description="Original HTML content")
    cleaned_markdown: str = Field(..., description="Cleaned Markdown output")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )
