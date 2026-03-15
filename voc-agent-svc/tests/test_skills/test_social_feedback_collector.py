"""Tests for SKL-VoCA-06: Social Feedback Collector."""

import pytest
from unittest.mock import AsyncMock

from app.skills.social_feedback_collector import SocialFeedbackCollector
from app.skills.models import SkillContext


@pytest.fixture
def collector(mock_tavily_client):
    """SocialFeedbackCollector with mocked Tavily client."""
    return SocialFeedbackCollector(tavily_client=mock_tavily_client)


@pytest.mark.unit
def test_meta_attributes(collector):
    """Skill meta has correct ID and name."""
    assert collector.meta.skill_id == "SKL-VoCA-06"
    assert collector.meta.name == "social_feedback_collector"
    assert "VIEWER" in collector.meta.allowed_roles


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_returns_feedback(
    collector, mock_tavily_client, basic_skill_context, basic_input_data
):
    """Skill returns social feedback when Tavily returns results."""
    mock_tavily_client.search = AsyncMock(
        return_value=[
            {
                "title": "Twitter mention",
                "url": "https://twitter.com/user/status/123",
                "content": "TestCorp has 500 likes on this post #TestCorp",
            }
        ]
    )
    result = await collector.execute(basic_input_data, basic_skill_context)
    assert result.success is True
    assert result.skill_id == "SKL-VoCA-06"
    assert "social_feedback" in result.data
    assert len(result.data["social_feedback"]) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_trend_cross_reference(
    collector, mock_tavily_client, basic_input_data
):
    """Skill cross-references TCIA trend data in previous_outputs."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="t1",
        user_role="EDITOR",
        previous_outputs={
            "trend_cultural": {
                "trends": [
                    {"topic": "AI automation"},
                    {"topic": "sustainability"},
                ],
                "cultural_signals": [
                    {"signal": "remote work adoption"},
                ],
            },
        },
        operating_mode="external_only",
    )
    mock_tavily_client.search = AsyncMock(
        return_value=[
            {
                "title": "Reddit post",
                "url": "https://reddit.com/r/tech/1",
                "content": "TestCorp is embracing AI automation and sustainability",
            }
        ]
    )
    result = await collector.execute(basic_input_data, ctx)
    assert result.success is True
    # At least one feedback item should be trend-driven
    trend_driven = [
        fb
        for fb in result.data["social_feedback"]
        if fb.get("is_trend_driven", False)
    ]
    assert len(trend_driven) > 0
