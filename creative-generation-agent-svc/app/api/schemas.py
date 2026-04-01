"""Pydantic v2 request/response models for the CGA service."""

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
    tenant_context: TenantContext | dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


# ── Response Sub-Models ──


class GeneratedImage(BaseModel):
    """A single AI-generated image."""

    ad_set_name: str = ""
    variant_id: str = ""
    aspect_ratio: str = ""  # "1:1", "9:16", "16:9"
    gcs_url: str = ""
    prompt_used: str = ""
    provider: str = "nano_banana_2"
    cost_usd: float = 0.0
    generation_time_ms: int = 0


class HookVariant(BaseModel):
    """Ad hook (first line) variant."""

    ad_set_name: str = ""
    hook_text: str = ""
    funnel_stage: str = ""  # "tofu", "mofu", "bofu"
    hook_type: str = ""  # "curiosity", "emotional", "pain_point", etc.
    scroll_stop_power: float = Field(0.0, ge=0, le=100)
    char_count: int = 0


class CopyVariant(BaseModel):
    """Primary ad copy variant."""

    ad_set_name: str = ""
    copy_text: str = ""
    funnel_stage: str = ""
    length_label: str = ""  # "short", "medium", "long"
    char_count: int = 0
    positioning_alignment: float = Field(0.0, ge=0, le=100)
    voice_consistency: float = Field(0.0, ge=0, le=100)


class CTAVariant(BaseModel):
    """Call-to-action variant."""

    ad_set_name: str = ""
    cta_button: str = ""  # Meta CTA enum: "LEARN_MORE", "SHOP_NOW", etc.
    cta_text: str = ""
    funnel_stage: str = ""
    urgency_score: float = Field(0.0, ge=0, le=100)
    clarity_score: float = Field(0.0, ge=0, le=100)


class ComplianceResult(BaseModel):
    """Meta Advertising Standards compliance check result."""

    variant_id: str = ""
    variant_type: str = ""  # "hook", "copy", "cta"
    status: str = "pass"  # "pass", "fail", "warning"
    violations: list[dict[str, Any]] = Field(default_factory=list)


class AdCreativeUnit(BaseModel):
    """Complete ad creative unit (image + copy + CTA)."""

    ad_set_name: str = ""
    variant_label: str = ""
    image_gcs_urls: dict[str, str] = Field(default_factory=dict)
    headline: str = ""
    primary_text: str = ""
    cta_button: str = ""
    cta_text: str = ""
    ad_format: str = ""  # "single_image", "carousel", "collection"
    image_copy_coherence: float = Field(0.0, ge=0, le=100)


class AdSetCreativePackage(BaseModel):
    """Creative package for a single ad set."""

    ad_set_name: str = ""
    persona_name: str = ""
    funnel_stage: str = ""
    ad_units: list[AdCreativeUnit] = Field(default_factory=list)
    approval_status: str = "auto_approved"  # v1: always auto-approved
    refinement_rounds: int = 0


# ── Main Response Model ──


class CGAResponse(BaseModel):
    """Full CGA analysis response."""

    query: str = ""
    creative_package: dict[str, Any] = Field(default_factory=dict)
    ad_set_packages: list[dict[str, Any]] = Field(default_factory=list)
    ad_units: list[dict[str, Any]] = Field(default_factory=list)
    generated_images: list[dict[str, Any]] = Field(default_factory=list)
    hooks: list[dict[str, Any]] = Field(default_factory=list)
    copy_variants: list[dict[str, Any]] = Field(default_factory=list)
    ctas: list[dict[str, Any]] = Field(default_factory=list)
    compliance_results: list[dict[str, Any]] = Field(default_factory=list)
    creative_profiles: list[dict[str, Any]] = Field(default_factory=list)
    total_images_generated: int = 0
    total_images_refined: int = 0
    image_gen_cost_usd: float = 0.0
    compliance_pass_rate: float = 0.0
    creative_quality_score: float = 0.0
    confidence_score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    # Context usage flags
    caa_context_used: bool = False
    wf1_context_used: bool = False
    bpa_context_used: bool = False
    bpv_context_used: bool = False
    nta_context_used: bool = False
    bsa_context_used: bool = False
    baa_context_used: bool = False
    company_context_used: bool = False
    image_gen_failed: bool = False
    gcs_uri: str = ""
    execution_time_ms: int = 0
