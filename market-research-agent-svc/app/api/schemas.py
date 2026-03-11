"""
Pydantic v2 request/response models for market-research-agent-svc.

The ExecuteRequest matches the payload sent by the orchestrator's
ExternalWrapper (pipeline-orchestrator-svc/app/nodes/external_wrapper.py).
"""

from typing import Any

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    """Tenant isolation context passed from the orchestrator."""

    tenant_id: str = ""
    gcs_raw_bucket: str = ""
    gcs_processed_bucket: str = ""
    rag_data_store_id: str = ""


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
    """A single source reference (web page, API, news article)."""

    type: str = Field(
        default="web", description="Source type: web, economic_data, news"
    )
    title: str = Field(default="", description="Title of the source")
    url: str = Field(default="", description="URL of the source")


class MarketResearchResponse(BaseModel):
    """
    Response body for POST /v1/execute.

    Contains structured market research output including market sizing,
    competitive landscape, industry trends, and economic indicators.
    The orchestrator stores this in node_outputs[node_id].
    ManagerNode aggregates 'findings' and 'recommendations'.
    """

    query: str = Field(default="", description="The research query")
    market_overview: str = Field(default="", description="High-level market summary")
    market_sizing: dict[str, Any] = Field(
        default_factory=dict, description="TAM/SAM/SOM estimates"
    )
    competitive_landscape: list[dict[str, Any]] = Field(
        default_factory=list, description="Competitor profiles"
    )
    industry_trends: list[str] = Field(
        default_factory=list, description="Key industry trends"
    )
    economic_indicators: dict[str, Any] = Field(
        default_factory=dict, description="Relevant economic data"
    )
    sources: list[SourceItem] = Field(
        default_factory=list, description="Source references"
    )
    findings: list[str] = Field(
        default_factory=list, description="Key findings from research"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    raw_context: str = Field(
        default="", description="Full raw context from all data sources"
    )
    confidence_score: float = Field(
        default=0.0, description="Quality confidence score 0.0-1.0"
    )
    methodology_notes: list[str] = Field(
        default_factory=list, description="Notes on research methodology used"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "0.1.0"
