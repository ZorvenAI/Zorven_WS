"""Pydantic models for the TCIA trend registry."""

from pydantic import BaseModel, Field


class TrendRegistryEntry(BaseModel):
    """A trend profile stored in the Redis registry."""

    trend_slug: str = ""
    topic: str = ""
    relevance_score: int = 0
    audience_alignment: int = 0
    competitive_landscape: int = 0
    brand_fit: int = 0
    momentum: int = 0
    recommendation: str = "monitor"
    platforms: list[str] = Field(default_factory=list)
    first_seen: str = ""
    last_updated: str = ""
    scan_count: int = 0


class TrendVelocity(BaseModel):
    """Detected velocity change for a trend."""

    trend_slug: str = ""
    direction: str = ""  # "new", "rising", "falling"
    delta: int = 0
    old_score: int = 0
    new_score: int = 0


class TrendScore(BaseModel):
    """A single historical score data point."""

    timestamp: float = 0.0
    score: int = 0
