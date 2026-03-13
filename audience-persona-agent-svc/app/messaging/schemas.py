"""Kafka event schemas for the Audience Persona Agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Event for the agent-trace-topic (ThoughtTrace UI)."""

    job_id: str = ""
    node_id: str = "audience_persona"
    status: str = ""
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AuditEvent(BaseModel):
    """Event for the audience-persona-audit-topic."""

    job_id: str = ""
    tenant_id: str = ""
    query: str = ""
    personas_count: int = 0
    journey_maps_count: int = 0
    sources_count: int = 0
    findings_count: int = 0
    confidence_score: float = 0.0
    data_sources_used: list[str] = Field(default_factory=list)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
