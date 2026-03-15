"""Tests for SKL-VoCA-09: Sentiment Analyzer."""

import pytest

from app.skills.sentiment_analyzer import SentimentAnalyzer
from app.skills.models import SkillContext


@pytest.fixture
def analyzer_no_llm():
    """SentimentAnalyzer without Anthropic client (stub mode)."""
    return SentimentAnalyzer(anthropic_client=None)


@pytest.mark.unit
def test_meta_attributes(analyzer_no_llm):
    """Skill meta has correct ID and name."""
    assert analyzer_no_llm.meta.skill_id == "SKL-VoCA-09"
    assert analyzer_no_llm.meta.name == "sentiment_analyzer"
    assert "VIEWER" not in analyzer_no_llm.meta.allowed_roles
    assert "EDITOR" in analyzer_no_llm.meta.allowed_roles
    assert analyzer_no_llm.meta.circuit_breaker_dependency == "llm"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_stub_mode_no_anthropic(analyzer_no_llm, basic_skill_context):
    """When Anthropic client is None, stub sentiment data is returned."""
    result = await analyzer_no_llm.execute(
        {"prompt": "Analyze sentiment", "feedback_data": {}},
        basic_skill_context,
    )
    assert result.success is True
    assert result.skill_id == "SKL-VoCA-09"
    assert "overall_sentiment" in result.data
    assert result.data["overall_sentiment"]["positive"] == 0.33
    assert "channel_sentiments" in result.data
    assert "message" in result.data
    assert "stub" in result.data["message"].lower() or "not available" in result.data["message"].lower()
