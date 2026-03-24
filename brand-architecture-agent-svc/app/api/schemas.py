"""Pydantic v2 request/response models for the Brand Architecture Agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# -- Request Models --


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


# -- Architecture Sub-Models --


class ModelEvaluation(BaseModel):
    """Evaluation of a single architecture model."""

    model: str = ""  # branded_house|house_of_brands|endorsed|hybrid|sub_brand
    positioning_alignment: float = 0.0  # 0-25
    audience_fit: float = 0.0  # 0-25
    competitive_diff: float = 0.0  # 0-25
    operational_efficiency: float = 0.0  # 0-25
    total: float = 0.0  # 0-100
    rationale: str = ""


class HierarchyNode(BaseModel):
    """A node in the brand hierarchy tree."""

    name: str = ""
    type: str = ""  # master|sub_brand|product_line|endorsed|independent
    relationship_to_parent: str = ""
    target_persona: str = ""
    positioning_score: float = 0.0
    visual_identity_guideline: str = ""
    children: list[HierarchyNode] = Field(default_factory=list)


class ArchitectureRecommendation(BaseModel):
    """Architecture model recommendation with scoring."""

    recommended_model: str = ""
    model_scores: list[ModelEvaluation] = Field(default_factory=list)
    why_not_others: list[dict[str, Any]] = Field(default_factory=list)
    confidence_score: float = 0.0
    citations: list[str] = Field(default_factory=list)


class BrandHierarchyTree(BaseModel):
    """Complete brand hierarchy tree."""

    root: HierarchyNode = Field(default_factory=HierarchyNode)
    total_depth: int = 0
    total_nodes: int = 0


class NamingHierarchy(BaseModel):
    """Naming conventions and consistency analysis."""

    naming_pattern: str = ""
    naming_rules: list[dict[str, Any]] = Field(default_factory=list)
    consistency_score: float = 0.0


class PortfolioGrowthPath(BaseModel):
    """Portfolio growth roadmap."""

    phases: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_risk_assessment: list[dict[str, Any]] = Field(default_factory=list)


# -- Main Response Model --


class BAAResponse(BaseModel):
    """Complete response from the Brand Architecture Agent."""

    query: str = ""
    recommendation: ArchitectureRecommendation = Field(
        default_factory=ArchitectureRecommendation
    )
    hierarchy: BrandHierarchyTree = Field(default_factory=BrandHierarchyTree)
    naming_hierarchy: NamingHierarchy = Field(default_factory=NamingHierarchy)
    growth_path: PortfolioGrowthPath = Field(default_factory=PortfolioGrowthPath)
    strategy: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    wf1_context_used: bool = False
    bpa_context_used: bool = False
    execution_time_ms: int = 0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)
