"""WF1 discovery & research scorers."""

from app.scorers.wf1.competitor_accuracy import competitor_accuracy
from app.scorers.wf1.market_completeness import market_completeness
from app.scorers.wf1.persona_quality import persona_quality
from app.scorers.wf1.trend_relevance import trend_relevance
from app.scorers.wf1.voca_sentiment import voca_sentiment

WF1_SCORERS = [
    market_completeness,
    competitor_accuracy,
    persona_quality,
    trend_relevance,
    voca_sentiment,
]

__all__ = [
    "WF1_SCORERS",
    "market_completeness",
    "competitor_accuracy",
    "persona_quality",
    "trend_relevance",
    "voca_sentiment",
]
