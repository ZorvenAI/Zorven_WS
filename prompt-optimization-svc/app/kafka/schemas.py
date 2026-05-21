"""Pydantic models for Kafka events."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Trace event for agent-trace-topic."""

    job_id: str = Field(..., description="Pipeline job ID")
    node_id: str = Field(default="prompt_optimization_worker")
    status: str = Field(default="PROCESSING")
    message: str = Field(...)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AuditEvent(BaseModel):
    """Audit event for poi-optimization-audit-topic."""

    job_id: str = Field(...)
    tenant_id: str = Field(...)
    action: str = Field(...)
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
