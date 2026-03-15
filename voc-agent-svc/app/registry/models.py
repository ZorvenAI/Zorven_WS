"""Domain models for the VoCA feedback registry."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Customer ID Hashing (Decision #5) ──


def hash_customer_id(customer_id: str | int, salt: str = "") -> str:
    """SHA-256 hash a customer ID for anonymization."""
    raw = f"{salt}:{customer_id}" if salt else str(customer_id)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Feedback Models ──


class FeedbackChannel(str, Enum):
    ODOO_HELPDESK = "odoo_helpdesk"
    ODOO_SURVEY = "odoo_survey"
    ODOO_CHATTER = "odoo_chatter"
    REVIEWS = "reviews"
    SOCIAL_MEDIA = "social_media"
    FORUMS = "forums"
    RAG_HISTORICAL = "rag_historical"


class FeedbackItem(BaseModel):
    """Base feedback item."""

    feedback_id: str = ""
    channel: FeedbackChannel = FeedbackChannel.REVIEWS
    customer_id_hash: str = ""
    text: str = ""
    timestamp: str = ""
    sentiment_label: str = ""
    sentiment_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewFeedback(FeedbackItem):
    """Feedback from review platforms (G2, Capterra, Trustpilot, Google)."""

    channel: FeedbackChannel = FeedbackChannel.REVIEWS
    platform: str = ""
    rating: float = 0.0
    verified: bool = False
    review_title: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)


class SocialFeedback(FeedbackItem):
    """Feedback from social media platforms."""

    channel: FeedbackChannel = FeedbackChannel.SOCIAL_MEDIA
    platform: str = ""
    engagement_count: int = 0
    is_trend_driven: bool = False
    hashtags: list[str] = Field(default_factory=list)


class ForumFeedback(FeedbackItem):
    """Feedback from forums (Reddit, Quora, industry forums)."""

    channel: FeedbackChannel = FeedbackChannel.FORUMS
    platform: str = ""
    thread_title: str = ""
    upvotes: int = 0
    is_feature_request: bool = False


class TicketFeedback(FeedbackItem):
    """Feedback from Odoo helpdesk tickets."""

    channel: FeedbackChannel = FeedbackChannel.ODOO_HELPDESK
    ticket_id: int = 0
    priority: str = ""
    stage: str = ""
    category: str = ""
    resolution_time_hours: float = 0.0


class SurveyFeedback(FeedbackItem):
    """Feedback from Odoo survey responses."""

    channel: FeedbackChannel = FeedbackChannel.ODOO_SURVEY
    survey_id: int = 0
    survey_title: str = ""
    question: str = ""
    answer: str = ""
    score: float | None = None
    is_nps_response: bool = False


class ChatterFeedback(FeedbackItem):
    """Feedback from Odoo CRM chatter messages."""

    channel: FeedbackChannel = FeedbackChannel.ODOO_CHATTER
    model: str = ""
    record_id: int = 0
    message_type: str = ""


class LinkedFeedback(BaseModel):
    """Feedback linked to an APA persona segment."""

    feedback_id: str = ""
    persona_slug: str = ""
    confidence: float = 0.0
    linking_method: str = ""


# ── Survey Profile (NPS Detection) ──


class SurveyFeedbackProfile(BaseModel):
    """Aggregated survey feedback with NPS detection."""

    survey_count: int = 0
    response_count: int = 0
    nps_questions_detected: int = 0
    nps_responses: list[SurveyFeedback] = Field(default_factory=list)
    nps_detection_confidence: float = 0.0
    non_nps_responses: list[SurveyFeedback] = Field(default_factory=list)


# ── Registry Models ──


class ThemeClusterEntry(BaseModel):
    """A theme cluster stored in the registry."""

    theme_slug: str = ""
    theme_name: str = ""
    feedback_count: int = 0
    severity_score: float = 0.0
    sentiment_positive: float = 0.0
    sentiment_neutral: float = 0.0
    sentiment_negative: float = 0.0
    sub_themes: list[str] = Field(default_factory=list)
    last_updated: str = ""


class NPSDataPoint(BaseModel):
    """An NPS data point for time-series tracking."""

    period: str = ""
    nps_score: float = 0.0
    promoters: int = 0
    passives: int = 0
    detractors: int = 0
    total_responses: int = 0


class DataCoverageEntry(BaseModel):
    """Data coverage score point."""

    timestamp: float = 0.0
    score: float = 0.0
    channels_active: list[str] = Field(default_factory=list)
    operating_mode: str = ""
