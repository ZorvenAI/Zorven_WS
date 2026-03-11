"""Kafka event schemas for market-research-agent-svc."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """
    Trace event for agent-trace-topic.

    Emitted at each step of the market research process for
    real-time UI updates via ThoughtTrace.
    """

    job_id: str = Field(..., description="Pipeline job ID")
    node_id: str = Field(
        default="market_research_worker", description="Node ID in the pipeline"
    )
    status: str = Field(
        default="PROCESSING", description="Event status (PROCESSING, COMPLETED, ERROR)"
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
    Audit event for market-research-audit-topic.

    Stores research query, sources used, and findings for compliance.
    """

    job_id: str = Field(..., description="Pipeline job ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    query: str = Field(..., description="Research query")
    sources_count: int = Field(default=0, description="Number of sources consulted")
    findings_count: int = Field(default=0, description="Number of findings produced")
    confidence_score: float = Field(default=0.0, description="Confidence score")
    data_sources_used: list[str] = Field(
        default_factory=list,
        description="Data sources used (tavily, world_bank, newsapi)",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )
