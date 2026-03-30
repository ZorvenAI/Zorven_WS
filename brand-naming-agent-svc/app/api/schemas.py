"""Pydantic v2 request/response models for the NTA service."""

from typing import Any

from pydantic import BaseModel, Field


# ── Request Models ──


class TenantContext(BaseModel):
    """Tenant context from orchestrator dispatch."""

    tenant_id: str = ""
    company_name: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""
    user_role: str = "VIEWER"


class ExecuteRequest(BaseModel):
    """Full orchestrator dispatch payload."""

    input_prompt: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: TenantContext | dict[str, Any] = Field(
        default_factory=dict
    )
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


# ── Response Sub-Models ──


class NameScore(BaseModel):
    """Multi-dimensional score for a name candidate."""

    linguistic: float = Field(0.0, ge=0, le=100)
    memorability: float = Field(0.0, ge=0, le=100)
    availability: float = Field(0.0, ge=0, le=100)
    strategy_alignment: float = Field(0.0, ge=0, le=100)
    overall: float = Field(0.0, ge=0, le=100)


class AvailabilityResult(BaseModel):
    """Availability check result for a name candidate."""

    domain_com: bool | None = None
    domain_io: bool | None = None
    domain_co: bool | None = None
    twitter: bool | None = None
    instagram: bool | None = None
    linkedin: bool | None = None
    trademark_clear: bool | None = None
    trademark_notes: str = ""


class NameCandidate(BaseModel):
    """Single brand name candidate."""

    name: str
    rationale: str = ""
    naming_type: str = ""  # e.g., descriptive, coined, metaphorical
    scores: NameScore = Field(default_factory=NameScore)
    availability: AvailabilityResult = Field(default_factory=AvailabilityResult)
    shortlisted: bool = False


class Tagline(BaseModel):
    """Tagline generated for a shortlisted name."""

    tagline: str
    name: str = ""
    emotional_appeal: str = ""
    memorability_score: float = Field(0.0, ge=0, le=100)
    positioning_alignment: str = ""


class NamingBrief(BaseModel):
    """Final naming brief with recommendation."""

    recommended_name: str = ""
    recommended_tagline: str = ""
    rationale: str = ""
    positioning_alignment: str = ""
    personality_alignment: str = ""
    architecture_fit: str = ""
    next_steps: list[str] = Field(default_factory=list)


# ── Main Response Model ──


class NTAResponse(BaseModel):
    """Full NTA analysis response."""

    query: str = ""
    name_candidates: list[NameCandidate | dict[str, Any]] = Field(
        default_factory=list
    )
    shortlisted_names: list[str] = Field(default_factory=list)
    taglines: list[Tagline | dict[str, Any]] = Field(default_factory=list)
    naming_brief: NamingBrief | dict[str, Any] = Field(default_factory=dict)
    availability_results: dict[str, Any] = Field(default_factory=dict)
    scoring_summary: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    wf1_context_used: bool = False
    bpa_context_used: bool = False
    bpv_context_used: bool = False
    baa_context_used: bool = False
    execution_time_ms: int = 0
