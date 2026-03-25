"""Pydantic v2 request/response models for the BPV service."""

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


class AakerDimension(BaseModel):
    """Single Aaker personality dimension."""

    dimension: str
    score: float = Field(ge=0, le=100)
    rationale: str = ""


class AakerProfile(BaseModel):
    """Aaker 5-dimension personality profile."""

    dimensions: list[AakerDimension] = Field(default_factory=list)
    primary_dimension: str = ""
    secondary_dimension: str = ""
    differentiation_score: float = 0.0


class ArchetypeSelection(BaseModel):
    """Jungian archetype selection."""

    primary: dict[str, Any] = Field(default_factory=dict)
    secondary: dict[str, Any] = Field(default_factory=dict)
    resonance_score: float = 0.0
    blend_rationale: str = ""


class ValueItem(BaseModel):
    """Single value entry."""

    name: str
    definition: str = ""
    behavioral_manifestation: str = ""


class ValuesHierarchy(BaseModel):
    """Values hierarchy with three tiers."""

    core: list[ValueItem] = Field(default_factory=list)
    supporting: list[ValueItem] = Field(default_factory=list)
    aspirational: list[ValueItem] = Field(default_factory=list)
    authenticity_score: float = 0.0


class EmotionalAttributeMap(BaseModel):
    """Per-persona emotional intensity map."""

    personas: list[dict[str, Any]] = Field(default_factory=list)
    consistency_score: float = 0.0


class VoiceMatrix(BaseModel):
    """Brand voice matrix."""

    tone_spectrum: list[dict[str, Any]] = Field(default_factory=list)
    vocabulary: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)
    humor: dict[str, Any] = Field(default_factory=dict)
    dos: list[str] = Field(default_factory=list)
    donts: list[str] = Field(default_factory=list)
    channel_adaptations: list[dict[str, Any]] = Field(default_factory=list)


class CharacterBrief(BaseModel):
    """Brand character brief — persona card + executive summary."""

    persona_card: dict[str, Any] = Field(default_factory=dict)
    executive_summary: str = ""
    positioning_alignment_score: float = 0.0


# ── Main Response Model ──


class BPVResponse(BaseModel):
    """Full BPV analysis response."""

    query: str = ""
    aaker_profile: AakerProfile | dict[str, Any] = Field(
        default_factory=dict
    )
    archetype: ArchetypeSelection | dict[str, Any] = Field(
        default_factory=dict
    )
    values_hierarchy: ValuesHierarchy | dict[str, Any] = Field(
        default_factory=dict
    )
    emotional_map: EmotionalAttributeMap | dict[str, Any] = Field(
        default_factory=dict
    )
    voice_matrix: VoiceMatrix | dict[str, Any] = Field(
        default_factory=dict
    )
    character_brief: CharacterBrief | dict[str, Any] = Field(
        default_factory=dict
    )
    confidence_score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    wf1_context_used: bool = False
    bpa_context_used: bool = False
    baa_context_used: bool = False
    execution_time_ms: int = 0
    sub_brand_constraint_applied: bool = False
