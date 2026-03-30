"""Pydantic v2 request/response models for the CAA service."""

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


class FunnelStage(BaseModel):
    """Single funnel stage mapping."""

    stage: str = ""  # "tofu", "mofu", "bofu", "retention"
    meta_objective: str = ""  # Meta API objective enum
    budget_pct: float = 0.0
    description: str = ""


class TargetingSpec(BaseModel):
    """Audience targeting specification for an ad set."""

    ad_set_name: str = ""
    funnel_stage: str = ""
    demographics: dict[str, Any] = Field(default_factory=dict)
    interests: list[str] = Field(default_factory=list)
    behaviors: list[str] = Field(default_factory=list)
    custom_audiences: list[str] = Field(default_factory=list)
    lookalike_audiences: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    estimated_audience_size: int = 0


class AdSetBlueprint(BaseModel):
    """Blueprint for a single ad set."""

    name: str = ""
    funnel_stage: str = ""
    objective: str = ""
    targeting: TargetingSpec = Field(default_factory=TargetingSpec)
    placements: list[str] = Field(default_factory=list)
    daily_budget: float = 0.0
    bid_strategy: str = ""
    optimization_goal: str = ""
    creative_briefs: list[dict[str, Any]] = Field(default_factory=list)


class CampaignBlueprint(BaseModel):
    """Full Meta campaign blueprint (campaign -> ad sets -> ads)."""

    campaign_name: str = ""
    campaign_objective: str = ""
    special_ad_category: str = ""
    buying_type: str = "AUCTION"
    daily_budget: float = 0.0
    bid_strategy: str = ""
    cbo_enabled: bool = False
    ad_sets: list[AdSetBlueprint] = Field(default_factory=list)


class TestVariant(BaseModel):
    """A/B test variant."""

    variable: str = ""
    variants: list[str] = Field(default_factory=list)
    sample_size_per_variant: int = 0
    duration_days: int = 7
    success_metric: str = ""
    priority: str = "medium"


class TestPlan(BaseModel):
    """A/B test plan for the campaign."""

    tests: list[TestVariant] = Field(default_factory=list)
    total_testing_budget_pct: float = 0.0
    total_variants: int = 0


class KPITargets(BaseModel):
    """KPI targets per funnel stage."""

    targets: dict[str, dict[str, float]] = Field(default_factory=dict)


class PerformanceProjections(BaseModel):
    """Campaign performance projections."""

    estimated_reach: int = 0
    estimated_impressions: int = 0
    estimated_clicks: int = 0
    estimated_conversions: int = 0
    projected_roas: float = 0.0
    confidence_range: dict[str, float] = Field(default_factory=dict)


# ── Main Response Model ──


class CAAResponse(BaseModel):
    """Full CAA analysis response."""

    query: str = ""
    blueprint: dict[str, Any] = Field(default_factory=dict)
    funnel_map: dict[str, Any] = Field(default_factory=dict)
    targeting_specs: list[dict[str, Any]] = Field(default_factory=list)
    placement_budget: dict[str, Any] = Field(default_factory=dict)
    test_plan: dict[str, Any] = Field(default_factory=dict)
    kpi_targets: dict[str, Any] = Field(default_factory=dict)
    performance_projections: dict[str, Any] = Field(default_factory=dict)
    risk_assessment: dict[str, Any] = Field(default_factory=dict)
    creative_briefs: list[dict[str, Any]] = Field(default_factory=list)
    special_ad_category: str = ""
    meta_api_compatible: bool = False
    confidence_score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    wf1_context_used: bool = False
    wf2_context_used: bool = False
    bpa_context_used: bool = False
    company_context_used: bool = False
    tavily_benchmarks_used: bool = False
    odoo_data_used: bool = False
    rag_learnings_used: bool = False
    gcs_uri: str = ""
    execution_time_ms: int = 0
