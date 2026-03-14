"""Pydantic v2 request/response schemas for the TCIA service."""

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Request ──


class TenantContext(BaseModel):
    tenant_id: str = ""
    user_role: str = "EDITOR"
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""

    model_config = {"extra": "allow"}


class ExecuteRequest(BaseModel):
    input_prompt: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)
    tenant_context: TenantContext = Field(default_factory=TenantContext)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


# ── Response sub-models ──


class ScoredTrend(BaseModel):
    trend_slug: str = ""
    topic: str = ""
    relevance_score: int = 0  # 0-100
    audience_alignment: int = 0  # 0-25
    competitive_landscape: int = 0  # 0-25
    brand_fit: int = 0  # 0-25
    momentum: int = 0  # 0-25
    recommendation: Literal["capitalize", "monitor", "avoid"] = "monitor"
    rationale: str = ""
    citations: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)


class TrendPersonaMapping(BaseModel):
    trend_slug: str = ""
    persona_slug: str = ""
    affinity_score: float = 0.0
    content_angles: list[str] = Field(default_factory=list)
    customer_segment_overlap: float = 0.0
    recommended_channels: list[str] = Field(default_factory=list)


class TrendPersonaMatrix(BaseModel):
    mappings: list[TrendPersonaMapping] = Field(default_factory=list)


class OpportunityAlert(BaseModel):
    alert_id: str = ""
    trend_slug: str = ""
    relevance_score: int = 0
    urgency: Literal["immediate", "this_week", "this_month"] = "this_month"
    recommendation: str = ""
    affected_personas: list[str] = Field(default_factory=list)
    suggested_response: str = ""
    expiry_estimate: str = ""


class SocialTrend(BaseModel):
    topic: str = ""
    platform: str = ""
    velocity_score: float = 0.0
    volume_estimate: int = 0
    hashtags: list[str] = Field(default_factory=list)
    sample_content_urls: list[str] = Field(default_factory=list)


class CulturalShift(BaseModel):
    domain: str = ""
    shift_description: str = ""
    evidence_strength: float = 0.0
    affected_demographics: list[str] = Field(default_factory=list)
    timeline_estimate: str = ""
    sources: list[dict[str, str]] = Field(default_factory=list)


class ViralPatternProfile(BaseModel):
    top_formats: list[str] = Field(default_factory=list)
    emotional_triggers: list[str] = Field(default_factory=list)
    amplification_mechanics: list[str] = Field(default_factory=list)
    platform_factors: list[dict[str, str]] = Field(default_factory=list)
    brand_safe_patterns: list[str] = Field(default_factory=list)
    brand_unsafe_patterns: list[str] = Field(default_factory=list)


class GenerationalProfile(BaseModel):
    generation: str = ""
    emerging_behaviors: list[str] = Field(default_factory=list)
    language_patterns: list[str] = Field(default_factory=list)
    platform_shifts: list[str] = Field(default_factory=list)
    brand_expectations: list[str] = Field(default_factory=list)
    subcultures: list[str] = Field(default_factory=list)
    relevance_to_personas: list[str] = Field(default_factory=list)


class SlangTerm(BaseModel):
    term: str = ""
    definition: str = ""
    origin_platform: str = ""
    adoption_stage: str = ""
    sensitivity_flag: bool = False


class LanguageTrendProfile(BaseModel):
    emerging_terms: list[SlangTerm] = Field(default_factory=list)
    fading_terms: list[str] = Field(default_factory=list)
    language_shifts: list[str] = Field(default_factory=list)


class TrendReport(BaseModel):
    executive_summary: str = ""
    trend_scorecard: list[ScoredTrend] = Field(default_factory=list)
    new_trends: list[str] = Field(default_factory=list)
    rising_trends: list[str] = Field(default_factory=list)
    fading_trends: list[str] = Field(default_factory=list)
    competitive_trend_gaps: list[str] = Field(default_factory=list)
    persona_trend_alignment: TrendPersonaMatrix | None = None
    strategic_recommendations: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    citations: list[str] = Field(default_factory=list)


class SourceItem(BaseModel):
    type: str = ""
    title: str = ""
    url: str = ""
    description: str = ""


# ── Main Response ──


class TrendInsightsResponse(BaseModel):
    trend_report: TrendReport = Field(default_factory=TrendReport)
    scored_trends: list[ScoredTrend] = Field(default_factory=list)
    trend_persona_matrix: TrendPersonaMatrix | None = None
    opportunity_alerts: list[OpportunityAlert] = Field(default_factory=list)
    viral_patterns: ViralPatternProfile | None = None
    cultural_shifts: list[CulturalShift] = Field(default_factory=list)
    generational_insights: list[GenerationalProfile] = Field(default_factory=list)
    language_trends: LanguageTrendProfile | None = None
    sources: list[SourceItem] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
