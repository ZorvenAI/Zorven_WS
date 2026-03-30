"""Pydantic v2 request/response models for the BSA service."""

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


class StoryVersion(BaseModel):
    """Single origin story version (short/medium/long)."""

    length_label: str = ""  # "short", "medium", "long"
    word_count_target: int = 0
    content: str = ""
    archetype_arc_alignment: float = Field(0.0, ge=0, le=1)
    emotional_resonance_score: float = Field(0.0, ge=0, le=1)
    voice_consistency_score: float = Field(0.0, ge=0, le=1)


class MissionVision(BaseModel):
    """Mission and vision statement pair."""

    mission: str = ""
    mission_scores: dict[str, float] = Field(default_factory=dict)
    vision: str = ""
    vision_scores: dict[str, float] = Field(default_factory=dict)
    existing_mission: str = ""
    existing_vision: str = ""
    refinement_notes: str = ""


class ElevatorPitch(BaseModel):
    """Elevator pitch at a specific duration."""

    duration_label: str = ""  # "15s", "30s", "60s"
    word_count: int = 0
    content: str = ""
    memorability_score: float = Field(0.0, ge=0, le=1)
    positioning_alignment: float = Field(0.0, ge=0, le=1)


class ChannelNarrative(BaseModel):
    """Channel-specific narrative adaptation."""

    channel: str = ""  # "website_about", "social_bio", "investor", "press"
    content: str = ""
    tone: str = ""
    word_count: int = 0


class StoryStyleGuide(BaseModel):
    """Narrative style guide for the brand."""

    narrative_principles: list[str] = Field(default_factory=list)
    approved_themes: list[str] = Field(default_factory=list)
    forbidden_themes: list[str] = Field(default_factory=list)
    tone_guidelines: dict[str, str] = Field(default_factory=dict)
    example_passages: list[str] = Field(default_factory=list)


class SubBrandStory(BaseModel):
    """Story variation for a sub-brand."""

    brand_context_id: str = ""
    brand_name: str = ""
    origin_story_short: str = ""
    positioning_hook: str = ""
    relationship_to_parent: str = ""


# ── Main Response Model ──


class BSAResponse(BaseModel):
    """Full BSA analysis response."""

    query: str = ""
    origin_story: dict[str, Any] = Field(default_factory=dict)
    mission_vision: dict[str, Any] = Field(default_factory=dict)
    pitches: dict[str, Any] = Field(default_factory=dict)
    channel_narratives: dict[str, Any] = Field(default_factory=dict)
    story_style_guide: dict[str, Any] = Field(default_factory=dict)
    subbrand_stories: list[dict[str, Any]] = Field(default_factory=list)
    narrative_package: dict[str, Any] = Field(default_factory=dict)
    wf2_strategy_summary: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    wf1_context_used: bool = False
    bpa_context_used: bool = False
    bpv_context_used: bool = False
    baa_context_used: bool = False
    nta_context_used: bool = False
    gcs_uri: str = ""
    execution_time_ms: int = 0
