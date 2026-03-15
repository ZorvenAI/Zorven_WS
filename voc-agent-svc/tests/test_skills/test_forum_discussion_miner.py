"""Tests for SKL-VoCA-07: Forum Discussion Miner."""

import pytest
from unittest.mock import AsyncMock

from app.skills.forum_discussion_miner import ForumDiscussionMiner


@pytest.fixture
def miner(mock_tavily_client):
    """ForumDiscussionMiner with mocked dependencies."""
    web_scraper = AsyncMock()
    web_scraper.scrape = AsyncMock(return_value="")
    return ForumDiscussionMiner(
        tavily_client=mock_tavily_client,
        web_scraper=web_scraper,
    )


@pytest.mark.unit
def test_meta_attributes(miner):
    """Skill meta has correct ID and name."""
    assert miner.meta.skill_id == "SKL-VoCA-07"
    assert miner.meta.name == "forum_discussion_miner"
    assert "VIEWER" in miner.meta.allowed_roles
    assert miner.meta.circuit_breaker_dependency == "tavily"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_returns_feedback(
    miner, mock_tavily_client, basic_skill_context, basic_input_data
):
    """Skill returns forum feedback when Tavily returns results."""
    mock_tavily_client.search = AsyncMock(
        return_value=[
            {
                "title": "Reddit: TestCorp review",
                "url": "https://reddit.com/r/saas/abc123",
                "content": (
                    "I wish TestCorp would add dark mode. "
                    "This is a frustrating missing feature. 42 upvotes"
                ),
            }
        ]
    )
    result = await miner.execute(basic_input_data, basic_skill_context)
    assert result.success is True
    assert result.skill_id == "SKL-VoCA-07"
    assert "forum_feedback" in result.data
    assert len(result.data["forum_feedback"]) > 0
