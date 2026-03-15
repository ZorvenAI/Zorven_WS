"""Tests for SKL-VoCA-05: External Review Miner."""

import pytest
from unittest.mock import AsyncMock

from app.skills.external_review_miner import ExternalReviewMiner


@pytest.fixture
def miner(mock_tavily_client):
    """ExternalReviewMiner with mocked dependencies."""
    web_scraper = AsyncMock()
    web_scraper.scrape = AsyncMock(return_value="")
    return ExternalReviewMiner(
        tavily_client=mock_tavily_client,
        web_scraper=web_scraper,
    )


@pytest.mark.unit
def test_meta_attributes(miner):
    """Skill meta has correct ID, name, and allowed_roles."""
    assert miner.meta.skill_id == "SKL-VoCA-05"
    assert miner.meta.name == "external_review_miner"
    assert "VIEWER" in miner.meta.allowed_roles
    assert miner.meta.circuit_breaker_dependency == "tavily"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_returns_reviews(
    miner, mock_tavily_client, basic_skill_context, basic_input_data
):
    """Skill returns review data when Tavily returns results."""
    mock_tavily_client.search = AsyncMock(
        return_value=[
            {
                "title": "G2 Review",
                "url": "https://g2.com/review/testcorp",
                "content": "Great product rated 4.5/5 stars verified",
            }
        ]
    )
    result = await miner.execute(basic_input_data, basic_skill_context)
    assert result.success is True
    assert result.skill_id == "SKL-VoCA-05"
    assert "own_reviews" in result.data
    assert len(result.data["own_reviews"]) > 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_empty_results(
    miner, mock_tavily_client, basic_skill_context, basic_input_data
):
    """Skill succeeds with empty reviews when search returns nothing."""
    mock_tavily_client.search = AsyncMock(return_value=[])
    result = await miner.execute(basic_input_data, basic_skill_context)
    assert result.success is True
    assert result.data["own_reviews"] == []
