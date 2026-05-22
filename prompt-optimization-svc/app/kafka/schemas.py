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


class PromptLifecycleEvent(BaseModel):
    """Lifecycle event for prompt-lifecycle-events topic."""

    event_type: str = Field(..., description="e.g. prompt.promoted, prompt.rejected")
    prompt_name: str = Field(...)
    version: int = Field(...)
    from_state: str = Field(...)
    to_state: str = Field(...)
    tenant_id: str | None = Field(default=None)
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
