"""Kafka event schemas for intelligence-agent-svc."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """
    Trace event for agent-trace-topic.

    Emitted at each step of the intelligence analysis for
    real-time UI updates via ThoughtTrace.
    """

    job_id: str = Field(..., description="Pipeline job ID")
    node_id: str = Field(
        default="intelligence_worker", description="Node ID in the pipeline"
    )
    status: str = Field(
        default="PROCESSING",
        description="Event status (PROCESSING, COMPLETE, ERROR)",
    )
    message: str = Field(..., description="Human-readable step description")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )


class ValuationAuditEvent(BaseModel):
    """
    Audit event for valuation-audit-logs topic.

    Stores math constants and methodology for legal defensibility
    of ISO 10668 brand valuations.
    """

    job_id: str = Field(..., description="Pipeline job ID")
    tenant_id: str = Field(..., description="Tenant identifier")
    methodology: str = Field(
        ..., description="Valuation methodology (royalty_relief, price_premium)"
    )
    royalty_rate: float = Field(..., description="Applied royalty rate")
    discount_rate: float = Field(..., description="Discount rate (WACC)")
    tax_rate: float = Field(..., description="Corporate tax rate")
    npv: float = Field(..., description="Calculated Net Present Value")
    bsi_score: int = Field(..., description="Brand Strength Index (0-100)")
    data_completeness: float = Field(
        ..., description="Fraction of data available (0.0-1.0)"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )
