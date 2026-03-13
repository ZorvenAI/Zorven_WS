"""Pydantic v2 request/response models for the Audience Persona Agent."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ── Request Models ──


class TenantContext(BaseModel):
    """Tenant context from the orchestrator."""

    model_config = {"extra": "allow"}

    tenant_id: str = ""
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


# ── Enums ──


class PersonaDataSource(str, Enum):
    """Source classification for persona data."""

    CRM_GROUNDED = "crm_grounded"
    RESEARCH_BASED = "research_based"


# ── Persona Sub-Models ──


class DemographicProfile(BaseModel):
    """Demographic attributes for a persona."""

    age_range: str = ""
    gender_distribution: str = ""
    income_range: str = ""
    education_level: str = ""
    location: str = ""
    job_titles: list[str] = Field(default_factory=list)
    company_size: str = ""
    industry: str = ""


class PsychographicProfile(BaseModel):
    """Psychographic and behavioral attributes."""

    values: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)
    lifestyle: str = ""
    personality_traits: list[str] = Field(default_factory=list)
    media_consumption: list[str] = Field(default_factory=list)
    social_platforms: list[str] = Field(default_factory=list)
    content_preferences: list[str] = Field(default_factory=list)
    decision_style: str = ""


class JourneyStage(BaseModel):
    """A single stage in the buying journey."""

    name: str = ""
    touchpoints: list[str] = Field(default_factory=list)
    info_needs: list[str] = Field(default_factory=list)
    emotional_state: str = ""
    decision_criteria: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    content_recommendations: list[str] = Field(default_factory=list)


class BuyingJourneyMap(BaseModel):
    """Complete buying journey for a persona."""

    persona_slug: str = ""
    stages: list[JourneyStage] = Field(default_factory=list)
    total_estimated_cycle_days: int = 0
    stage_model_used: str = ""
    citations: list[str] = Field(default_factory=list)


class PersonaProfile(BaseModel):
    """A fully constructed buyer persona."""

    slug: str = ""
    segment_label: str = ""
    customer_count: int = 0
    revenue_contribution_pct: float = 0.0
    representative_partner_ids: list[int] = Field(default_factory=list)
    demographics: DemographicProfile = Field(default_factory=DemographicProfile)
    psychographics: PsychographicProfile = Field(default_factory=PsychographicProfile)
    pain_points: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    preferred_channels: list[str] = Field(default_factory=list)
    priority_score: float = 0.0
    narrative: str = ""
    data_source: PersonaDataSource = PersonaDataSource.RESEARCH_BASED
    confidence_score: float = 0.0
    citations: list[str] = Field(default_factory=list)


# ── Research Sub-Models ──


class BuyerRoleSignal(BaseModel):
    """Buyer role identified from research."""

    role: str = ""
    influence_level: str = ""
    decision_authority: str = ""
    typical_concerns: list[str] = Field(default_factory=list)
    evidence: str = ""


class CommunityProfile(BaseModel):
    """Community/forum research findings."""

    platform: str = ""
    topics: list[str] = Field(default_factory=list)
    sentiment: str = ""
    pain_points: list[str] = Field(default_factory=list)
    unmet_needs: list[str] = Field(default_factory=list)


class NeedsProfile(BaseModel):
    """Customer needs extracted from reviews."""

    category: str = ""
    needs: list[str] = Field(default_factory=list)
    frustrations: list[str] = Field(default_factory=list)
    competitor_mentions: list[str] = Field(default_factory=list)
    sentiment_summary: str = ""


class SocialBehaviorProfile(BaseModel):
    """Social listening analysis results."""

    platform: str = ""
    audience_size_estimate: str = ""
    engagement_patterns: list[str] = Field(default_factory=list)
    content_themes: list[str] = Field(default_factory=list)
    influencer_types: list[str] = Field(default_factory=list)


class SurveyProfile(BaseModel):
    """Odoo survey data extraction results."""

    survey_count: int = 0
    response_count: int = 0
    demographics_summary: dict[str, Any] = Field(default_factory=dict)
    satisfaction_scores: dict[str, float] = Field(default_factory=dict)
    nps_score: float | None = None
    key_themes: list[str] = Field(default_factory=list)


class CustomerSegment(BaseModel):
    """CRM customer segment."""

    segment_label: str = ""
    customer_count: int = 0
    industries: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    avg_revenue: float = 0.0
    win_rate: float = 0.0


class CRMSegmentProfile(BaseModel):
    """Odoo CRM extraction results."""

    customer_count: int = 0
    segment_count: int = 0
    has_sufficient_data: bool = False
    segments: list[CustomerSegment] = Field(default_factory=list)
    revenue_distribution: dict[str, float] = Field(default_factory=dict)
    top_industries: list[str] = Field(default_factory=list)


class SourceItem(BaseModel):
    """A research source reference."""

    title: str = ""
    url: str = ""
    snippet: str = ""


# ── Main Response Model ──


class AudiencePersonaResponse(BaseModel):
    """Complete response from the Audience Persona Agent."""

    query: str = ""
    personas: list[PersonaProfile] = Field(default_factory=list)
    journey_maps: list[BuyingJourneyMap] = Field(default_factory=list)
    segment_matrix: dict[str, Any] = Field(default_factory=dict)
    executive_summary: str = ""
    sources: list[SourceItem] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    raw_context: str = ""
    confidence_score: float = 0.0
    methodology_notes: str = ""
