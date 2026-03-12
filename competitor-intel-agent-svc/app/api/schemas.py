"""
Pydantic v2 request/response models for competitor-intel-agent-svc.

The ExecuteRequest matches the payload sent by the orchestrator's
ExternalWrapper (pipeline-orchestrator-svc/app/nodes/external_wrapper.py).
"""

from typing import Any

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    """Tenant isolation context passed from the orchestrator."""

    model_config = {"extra": "allow"}

    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""
    user_role: str = "EDITOR"


class ExecuteRequest(BaseModel):
    """
    Request body for POST /v1/execute.

    Matches the payload the orchestrator's ExternalWrapper sends:
    {input_prompt, input_context, tenant_context, config, previous_outputs}
    """

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


class SourceItem(BaseModel):
    """A single source reference (web page, API, review site)."""

    type: str = Field(
        default="web", description="Source type: web, review, social, pricing"
    )
    title: str = Field(default="", description="Title of the source")
    url: str = Field(default="", description="URL of the source")
    snippet: str = Field(default="", description="Relevant excerpt")


class CompetitorProfile(BaseModel):
    """A profiled competitor with structured data."""

    slug: str = Field(default="", description="URL-safe competitor identifier")
    name: str = Field(default="", description="Competitor name")
    website: str = Field(default="", description="Competitor website URL")
    description: str = Field(default="", description="Brief description")
    market_position: str = Field(default="", description="leader/challenger/niche/emerging")
    confidence: float = Field(default=0.0, description="Profile confidence 0.0-1.0")
    website_profile: dict[str, Any] = Field(
        default_factory=dict, description="Website profiling data"
    )
    social_presence: dict[str, Any] = Field(
        default_factory=dict, description="Social media metrics"
    )
    review_profile: dict[str, Any] = Field(
        default_factory=dict, description="Customer review aggregation"
    )
    pricing_profile: dict[str, Any] = Field(
        default_factory=dict, description="Pricing strategy data"
    )
    market_share_estimate: dict[str, Any] = Field(
        default_factory=dict, description="Estimated market share"
    )
    swot: dict[str, Any] = Field(
        default_factory=dict, description="SWOT analysis"
    )


class CompetitorIntelligenceResponse(BaseModel):
    """
    Response body for POST /v1/execute.

    Contains structured competitive intelligence output including competitor
    profiles, SWOT analyses, positioning gaps, and benchmarking report.
    The orchestrator stores this in node_outputs[node_id].
    ManagerNode aggregates 'findings' and 'recommendations'.
    """

    query: str = Field(default="", description="The analysis query")
    executive_summary: str = Field(
        default="", description="High-level competitive intelligence summary"
    )
    competitors: list[CompetitorProfile] = Field(
        default_factory=list, description="Profiled competitor list"
    )
    competitors_analyzed: list[str] = Field(
        default_factory=list,
        description="Names of competitors analyzed (for summary rendering)",
    )
    competitor_matrix: dict[str, Any] = Field(
        default_factory=dict, description="Comparative matrix across dimensions"
    )
    swot_analyses: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-competitor SWOT analyses with strengths, weaknesses, opportunities, threats",
    )
    positioning_gaps: list[dict[str, Any]] = Field(
        default_factory=list, description="Identified positioning gaps and opportunities"
    )
    positioning_map: dict[str, Any] = Field(
        default_factory=dict, description="Positioning map data (axes + positions)"
    )
    benchmarking_report: dict[str, Any] = Field(
        default_factory=dict, description="Full competitive benchmarking report"
    )
    sources: list[SourceItem] = Field(
        default_factory=list, description="Source references"
    )
    findings: list[str] = Field(
        default_factory=list, description="Key findings from analysis"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Strategic recommendations"
    )
    raw_context: str = Field(
        default="", description="Full raw context from all data sources"
    )
    confidence_score: float = Field(
        default=0.0, description="Quality confidence score 0.0-1.0"
    )
    methodology_notes: list[str] = Field(
        default_factory=list, description="Notes on analysis methodology used"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
