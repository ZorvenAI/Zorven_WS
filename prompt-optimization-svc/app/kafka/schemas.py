"""Pydantic models for Kafka events (§8.1, §8.2)."""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Lifecycle event type constants ──

PROMPT_REGISTERED = "prompt.registered"
OPTIMIZATION_STARTED = "prompt.optimization.started"
OPTIMIZATION_COMPLETED = "prompt.optimization.completed"
PROMPT_PROMOTED = "prompt.promoted"
VALIDATION_FAILED = "prompt.validation.failed"
PROMPT_ROLLED_BACK = "prompt.rolled_back"
PROMPT_REJECTED = "prompt.rejected"
OPTIMIZATION_RUN_APPROVED = "optimization.run.approved"
OPTIMIZATION_RUN_REJECTED = "optimization.run.approval_rejected"
SCHEMA_CHANGE_DETECTED = "prompt.schema_change_detected"

SCHEMA_VERSION = "1.0"


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
    """Lifecycle event for prompt-lifecycle-events topic (§8.2).

    correlation_id is used as the Kafka message key for idempotent
    deduplication (AC-4).
    """

    event_type: str = Field(..., description="e.g. prompt.promoted")
    prompt_name: str = Field(...)
    version: int = Field(...)
    from_state: str = Field(...)
    to_state: str = Field(...)
    tenant_id: str | None = Field(default=None)
    agent_code: str = Field(default="")
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event ID for dedup (AC-4)",
    )
    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="Schema version header (AC-3), pinned to 1.0",
    )

    @field_validator("correlation_id")
    @classmethod
    def correlation_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("correlation_id must be non-empty (AC-4)")
        return v

    @field_validator("schema_version")
    @classmethod
    def schema_version_pinned(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be '{SCHEMA_VERSION}', got '{v}' (AC-3)"
            )
        return v

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SchemaChangeEvent(BaseModel):
    """Event emitted when skill schema changes are detected (US-056)."""

    event_type: str = Field(default=SCHEMA_CHANGE_DETECTED)
    prompt_name: str = Field(...)
    agent_code: str = Field(...)
    skill_id: str = Field(...)
    changes: list[dict[str, Any]] = Field(..., description="List of SchemaChange dicts")
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event ID for dedup (AC-4)",
    )
    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="Schema version header (AC-3), pinned to 1.0",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("correlation_id")
    @classmethod
    def correlation_id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("correlation_id must be non-empty (AC-4)")
        return v

    @field_validator("schema_version")
    @classmethod
    def schema_version_pinned(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be '{SCHEMA_VERSION}', got '{v}' (AC-3)"
            )
        return v


class AuditEvent(BaseModel):
    """Audit event for poi-optimization-audit-topic."""

    job_id: str = Field(...)
    tenant_id: str = Field(...)
    action: str = Field(...)
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
