"""Pydantic v2 request/response models for the Voice of Customer Agent."""

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


class OperatingMode(str, Enum):
    """VoCA operating mode based on Odoo availability."""

    FULL = "full"
    EXTERNAL_ONLY = "external_only"


class DataProvenance(str, Enum):
    """Source classification for feedback data."""

    INTERNAL = "internal"
    EXTERNAL = "external"
    NOT_CONNECTED = "not_connected"


class FeedbackChannel(str, Enum):
    """Feedback data channels."""

    ODOO_HELPDESK = "odoo_helpdesk"
    ODOO_SURVEY = "odoo_survey"
    ODOO_CHATTER = "odoo_chatter"
    REVIEWS = "reviews"
    SOCIAL_MEDIA = "social_media"
    FORUMS = "forums"
    RAG_HISTORICAL = "rag_historical"


# ── Sentiment Sub-Models ──


class SentimentDistribution(BaseModel):
    """Sentiment breakdown."""

    positive: float = 0.0
    neutral: float = 0.0
    negative: float = 0.0


class EmotionProfile(BaseModel):
    """Emotion detection results."""

    joy: float = 0.0
    trust: float = 0.0
    surprise: float = 0.0
    anticipation: float = 0.0
    anger: float = 0.0
    fear: float = 0.0
    sadness: float = 0.0
    disgust: float = 0.0


class ChannelSentiment(BaseModel):
    """Per-channel sentiment analysis."""

    channel: str = ""
    provenance: DataProvenance = DataProvenance.EXTERNAL
    sentiment: SentimentDistribution = Field(
        default_factory=SentimentDistribution
    )
    feedback_count: int = 0
    confidence: float = 0.0


class SentimentAnalysis(BaseModel):
    """Multi-dimensional sentiment analysis results."""

    overall_sentiment: SentimentDistribution = Field(
        default_factory=SentimentDistribution
    )
    emotion_profile: EmotionProfile = Field(default_factory=EmotionProfile)
    channel_sentiments: list[ChannelSentiment] = Field(default_factory=list)
    persona_sentiments: dict[str, SentimentDistribution] = Field(
        default_factory=dict
    )
    trend_direction: str = ""
    data_coverage_score: float = 0.0


# ── Theme Sub-Models ──


class SubTheme(BaseModel):
    """Sub-theme within a theme cluster."""

    name: str = ""
    feedback_count: int = 0
    sentiment: SentimentDistribution = Field(
        default_factory=SentimentDistribution
    )
    representative_quotes: list[str] = Field(default_factory=list)


class ThemeCluster(BaseModel):
    """Hierarchical theme cluster."""

    theme_slug: str = ""
    theme_name: str = ""
    feedback_count: int = 0
    severity_score: float = 0.0
    sentiment: SentimentDistribution = Field(
        default_factory=SentimentDistribution
    )
    sub_themes: list[SubTheme] = Field(default_factory=list)
    representative_quotes: list[str] = Field(default_factory=list)
    competitor_correlation: str = ""
    market_context: str = ""


class ThemeClusterMap(BaseModel):
    """Complete theme clustering results."""

    themes: list[ThemeCluster] = Field(default_factory=list)
    total_feedback_analyzed: int = 0
    clustering_method: str = ""


# ── NPS Sub-Models ──


class NPSBreakdown(BaseModel):
    """NPS score breakdown."""

    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    nps_score: float = 0.0
    total_responses: int = 0


class NPSTrendAnalysis(BaseModel):
    """NPS trend analysis results."""

    nps_available: bool = False
    current_nps: NPSBreakdown = Field(default_factory=NPSBreakdown)
    proxy_nps: NPSBreakdown | None = None
    trend_periods: list[dict[str, Any]] = Field(default_factory=list)
    drivers: list[str] = Field(default_factory=list)
    detractor_themes: list[str] = Field(default_factory=list)
    data_source: str = ""


# ── Pain Point Sub-Models ──


class PainPoint(BaseModel):
    """A ranked pain point."""

    name: str = ""
    severity: float = 0.0
    frequency: int = 0
    persona_impact: list[str] = Field(default_factory=list)
    competitor_gap: str = ""
    trend_alignment: str = ""
    recommended_action: str = ""


class PainPointPriorityMatrix(BaseModel):
    """Ranked pain point matrix."""

    pain_points: list[PainPoint] = Field(default_factory=list)
    methodology: str = ""


# ── Strategy Bridge Sub-Models ──


class VoCStrategyBridge(BaseModel):
    """VoC-to-strategy bridge document."""

    executive_summary: str = ""
    pain_point_priority_matrix: PainPointPriorityMatrix = Field(
        default_factory=PainPointPriorityMatrix
    )
    voc_health_score: float = 0.0
    voc_health_breakdown: dict[str, float] = Field(default_factory=dict)
    operating_mode: str = ""
    odoo_onboarding_recommendation: str = ""
    cross_agent_insights: dict[str, str] = Field(default_factory=dict)
    strategic_recommendations: list[str] = Field(default_factory=list)


# ── Source Reference ──


class SourceItem(BaseModel):
    """A research source reference."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    channel: str = ""
    provenance: str = ""


# ── Main Response Model ──


class VoCAResponse(BaseModel):
    """Complete response from the Voice of Customer Agent."""

    query: str = ""
    operating_mode: str = ""
    data_coverage_score: float = 0.0
    sentiment: SentimentAnalysis = Field(default_factory=SentimentAnalysis)
    themes: ThemeClusterMap = Field(default_factory=ThemeClusterMap)
    nps_analysis: NPSTrendAnalysis = Field(default_factory=NPSTrendAnalysis)
    pain_point_priority_matrix: PainPointPriorityMatrix = Field(
        default_factory=PainPointPriorityMatrix
    )
    strategy_bridge: VoCStrategyBridge = Field(
        default_factory=VoCStrategyBridge
    )
    voc_health_score: float = 0.0
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[SourceItem] = Field(default_factory=list)
    confidence_score: float = 0.0
    raw_context: str = ""
