"""Tests for VoCA prompt loading integration."""

from unittest.mock import AsyncMock

import pytest

from app.prompts.fallbacks import (
    FALLBACK_MAP,
    FALLBACK_SYNTHESIS,
    FALLBACK_SENTIMENT,
)
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-2: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_synthesis_defined(self):
        assert FALLBACK_SYNTHESIS is not None
        assert len(FALLBACK_SYNTHESIS) > 20

    def test_fallback_map_has_synthesis_prompt(self):
        assert "zorven-wf1-voca-synthesis" in FALLBACK_MAP

    def test_fallback_sentiment_defined(self):
        assert FALLBACK_SENTIMENT is not None
        assert len(FALLBACK_SENTIMENT) > 20

    def test_fallback_map_has_sentiment_prompt(self):
        assert "zorven-wf1-voca-sentiment-analysis" in FALLBACK_MAP


    def test_all_fallbacks_non_empty(self):
        for name, template in FALLBACK_MAP.items():
            assert len(template) > 0, f"Empty fallback: {name}"

    def test_fallback_map_has_at_least_3_entries(self):
        assert len(FALLBACK_MAP) >= 5


class TestAgentPromptClient:
    """Test prompt loading through AgentPromptClient."""

    @pytest.fixture
    def client(self):
        c = AgentPromptClient(
            redis_url="redis://localhost:6379/2",
            mlflow_uri="http://localhost:5000",
        )
        c._redis = AsyncMock()
        c._http = AsyncMock()
        return c

    async def test_cache_hit_returns_template(self, client):
        """Tier 1: Cache hit returns template without MLflow call."""
        client._redis.get = AsyncMock(return_value="Cached VoCA prompt")
        result = await client.load(
            "zorven-wf1-voca-synthesis",
            fallback=FALLBACK_SYNTHESIS,
        )
        assert "Cached VoCA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-2: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None  # MLflow unavailable
        result = await client.load(
            "zorven-wf1-voca-synthesis",
            fallback=FALLBACK_SYNTHESIS,
        )
        assert result == FALLBACK_SYNTHESIS

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        """AC-2: Both Redis and MLflow unreachable."""
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf1-voca-synthesis",
            fallback=FALLBACK_SYNTHESIS,
        )
        assert result == FALLBACK_SYNTHESIS

    async def test_format_applies_variables(self, client):
        """Variables are applied to loaded template."""
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf1-voca-synthesis",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result
