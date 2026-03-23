"""Pydantic v2 request/response models for the Brand Positioning Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Request Models ──


class TenantContext(BaseModel):
    """Tenant context from the orchestrator."""

    model_config = {"extra": "allow"}

    tenant_id: str = ""
    company_name: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""
    user_role: str = "EDITOR"


class ExecuteRequest(BaseModel):
    """Orchestrator dispatch payload."""

    input_prompt: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: TenantContext = Field(default_factory=TenantContext)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


# ── Positioning Sub-Models ──


class PositioningStatement(BaseModel):
    """A single positioning statement candidate."""

    statement: str = ""
    framework_used: str = ""
    framework_rationale: str = ""
    target_audience: str = ""
    need: str = ""
    category: str = ""
    key_benefit: str = ""
    reason_to_believe: str = ""
    scores: dict[str, float] = Field(default_factory=dict)
    data_citations: list[str] = Field(default_factory=list)


class PerceptualMap(BaseModel):
    """A perceptual map with competitive positioning."""

    map_id: str = ""
    dimension_x: str = ""
    dimension_y: str = ""
    entities: list[dict[str, Any]] = Field(default_factory=list)
    migration_vector: dict[str, float] = Field(default_factory=dict)
    white_space_highlighted: list[dict[str, Any]] = Field(default_factory=list)
    differentiation_potential_score: float = 0.0
    is_primary_recommended: bool = False


class ValuePropositionCanvas(BaseModel):
    """Osterwalder Value Proposition Canvas."""

    customer_profile: dict[str, Any] = Field(default_factory=dict)
    value_map: dict[str, Any] = Field(default_factory=dict)
    fit_score: float = 0.0
    fit_analysis: str = ""


class DifferentiationFramework(BaseModel):
    """Points of Parity/Difference framework."""

    pops: list[dict[str, Any]] = Field(default_factory=list)
    pods: list[dict[str, Any]] = Field(default_factory=list)
    rtbs: list[dict[str, Any]] = Field(default_factory=list)
    proof_points: list[dict[str, Any]] = Field(default_factory=list)
    competitive_vulnerabilities: list[dict[str, Any]] = Field(default_factory=list)
    overall_differentiation_score: float = 0.0


class PositioningStrategy(BaseModel):
    """Full positioning strategy document."""

    executive_summary: str = ""
    recommended_positioning: PositioningStatement = Field(
        default_factory=PositioningStatement
    )
    alternative_positions: list[PositioningStatement] = Field(default_factory=list)
    canvas: ValuePropositionCanvas = Field(default_factory=ValuePropositionCanvas)
    perceptual_maps: list[PerceptualMap] = Field(default_factory=list)
    differentiation: DifferentiationFramework = Field(
        default_factory=DifferentiationFramework
    )
    implementation_guidelines: list[str] = Field(default_factory=list)
    risk_assessment: list[dict[str, Any]] = Field(default_factory=list)
    wf1_data_summary: dict[str, Any] = Field(default_factory=dict)


# ── Main Response Model ──


class BPAResponse(BaseModel):
    """Complete response from the Brand Positioning Agent."""

    query: str = ""
    recommended_positioning: PositioningStatement = Field(
        default_factory=PositioningStatement
    )
    alternative_positions: list[PositioningStatement] = Field(default_factory=list)
    positioning_candidates: list[PositioningStatement] = Field(default_factory=list)
    canvas: dict[str, Any] = Field(default_factory=dict)
    perceptual_maps: list[PerceptualMap] = Field(default_factory=list)
    differentiation: dict[str, Any] = Field(default_factory=dict)
    strategy: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    wf1_context_used: bool = False
    execution_time_ms: int = 0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)
