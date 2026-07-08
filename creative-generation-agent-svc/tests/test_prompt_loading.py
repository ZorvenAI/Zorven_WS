"""Tests for CGA prompt loading integration."""

from unittest.mock import AsyncMock

import pytest

from app.prompts.fallbacks import FALLBACK_COPYWRITING, FALLBACK_CREATIVE_DIRECTOR, FALLBACK_MAP
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-1: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_creative_director_defined(self):
        assert FALLBACK_CREATIVE_DIRECTOR is not None
        assert len(FALLBACK_CREATIVE_DIRECTOR) > 20

    def test_fallback_map_has_creative_director_prompt(self):
        assert "zorven-wf3-cga-creative-director" in FALLBACK_MAP

    def test_fallback_copywriting_defined(self):
        assert FALLBACK_COPYWRITING is not None
        assert len(FALLBACK_COPYWRITING) > 20

    def test_fallback_map_has_copywriting_prompt(self):
        assert "zorven-wf3-cga-copywriting" in FALLBACK_MAP


    def test_all_fallbacks_non_empty(self):
        for name, template in FALLBACK_MAP.items():
            assert len(template) > 0, f"Empty fallback: {name}"

    def test_fallback_map_has_at_least_3_entries(self):
        assert len(FALLBACK_MAP) >= 3


class TestAgentPromptClient:
    """Test prompt loading through AgentPromptClient."""

    @pytest.fixture
    def client(self):
        c = AgentPromptClient(
            redis_url="redis://localhost:6379/2",
            mlflow_uri="http://localhost:5000",
            fallback_only=False,
        )
        c._redis = AsyncMock()
        c._http = AsyncMock()
        return c

    async def test_cache_hit_returns_template(self, client):
        client._redis.get = AsyncMock(return_value="Cached CGA prompt")
        result = await client.load(
            "zorven-wf3-cga-creative-director",
            fallback=FALLBACK_CREATIVE_DIRECTOR,
        )
        assert "Cached CGA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-1: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None
        result = await client.load(
            "zorven-wf3-cga-creative-director",
            fallback=FALLBACK_CREATIVE_DIRECTOR,
        )
        assert result == FALLBACK_CREATIVE_DIRECTOR

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf3-cga-creative-director",
            fallback=FALLBACK_CREATIVE_DIRECTOR,
        )
        assert result == FALLBACK_CREATIVE_DIRECTOR

    async def test_format_applies_variables(self, client):
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf3-cga-creative-director",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result
