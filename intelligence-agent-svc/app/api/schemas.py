"""
Pydantic v2 request/response models for the intelligence agent API.

ExecuteRequest matches the orchestrator ExternalWrapper payload exactly.
ExecuteResponse includes findings + recommendations (required for ManagerNode
aggregation) plus valuation-specific fields.
"""

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Tenant context (same as discovery-agent-svc)
# ---------------------------------------------------------------------------


class TenantContext(BaseModel):
    """Tenant isolation context passed from the orchestrator."""

    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""


# ---------------------------------------------------------------------------
# Request model (identical to discovery-agent-svc)
# ---------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    """Request body for POST /v1/execute, /v1/iso-calc, /v1/analyze."""

    input_prompt: str = Field(..., description="The user's query or analysis request")
    input_context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context from the user"
    )
    tenant_context: TenantContext | dict[str, Any] = Field(
        default_factory=dict,
        description="Tenant isolation data (GCS buckets, RAG store)",
    )
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Node-level config merged with global_config",
    )
    previous_outputs: dict[str, Any] = Field(
        default_factory=dict, description="Outputs from upstream pipeline nodes"
    )


# ---------------------------------------------------------------------------
# Response models — ISO valuation + analysis
# ---------------------------------------------------------------------------


class PillarScore(BaseModel):
    """A single BSI pillar score."""

    name: str = Field(..., description="Pillar name: financial, behavioral, or legal")
    weight: float = Field(..., description="Pillar weight (0.0–1.0)")
    score: float = Field(..., description="Pillar score (0–100)")
    rationale: str = Field(
        default="", description="Explanation of the score derivation"
    )


class BSIResult(BaseModel):
    """Brand Strength Index result."""

    score: int = Field(..., description="Overall BSI score (0–100)")
    pillars: list[PillarScore] = Field(
        default_factory=list, description="Per-pillar breakdown"
    )
    data_completeness: float = Field(
        default=1.0, description="Fraction of data available (0.0–1.0)"
    )


class ValuationResult(BaseModel):
    """Royalty Relief brand valuation result."""

    brand_value_npv: float = Field(..., description="Net Present Value of brand")
    royalty_rate: float = Field(..., description="Applied royalty rate")
    discount_rate: float = Field(..., description="Discount rate (WACC)")
    tax_rate: float = Field(..., description="Corporate tax rate applied")
    horizon_years: int = Field(..., description="Forecast horizon in years")
    annual_royalties: list[float] = Field(
        default_factory=list, description="Post-tax royalty per year"
    )
    methodology: str = Field(
        default="royalty_relief", description="Valuation methodology used"
    )


class ExecuteResponse(BaseModel):
    """Response body for all intelligence endpoints.

    Always includes findings + recommendations for ManagerNode compatibility.
    """

    findings: list[str] = Field(
        default_factory=list, description="Key findings from the analysis"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    valuation: ValuationResult | None = Field(
        default=None, description="ISO 10668 valuation result (iso-calc only)"
    )
    bsi: BSIResult | None = Field(
        default=None, description="Brand Strength Index result"
    )
    methodology: str = Field(
        default="", description="Methodology used for the analysis"
    )
    rationale: str = Field(
        default="", description="Step-by-step reasoning and assumptions"
    )
    analysis_type: str = Field(
        default="", description="Type: iso_valuation | competitive_gap | general"
    )
    gap_analysis: dict[str, Any] | None = Field(
        default=None, description="Competitive gap analysis details"
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
