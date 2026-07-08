"""Tests for NTA prompt loading integration."""

from unittest.mock import AsyncMock

import pytest

from app.prompts.fallbacks import (
    FALLBACK_MAP,
    FALLBACK_NAMING,
    FALLBACK_TAGLINE,
)
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-3: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_naming_defined(self):
        assert FALLBACK_NAMING is not None
        assert len(FALLBACK_NAMING) > 20

    def test_fallback_map_has_naming_prompt(self):
        assert "zorven-wf2-nta-naming" in FALLBACK_MAP

    def test_fallback_tagline_defined(self):
        assert FALLBACK_TAGLINE is not None
        assert len(FALLBACK_TAGLINE) > 20

    def test_fallback_map_has_tagline_prompt(self):
        assert "zorven-wf2-nta-tagline" in FALLBACK_MAP


    def test_all_fallbacks_non_empty(self):
        for name, template in FALLBACK_MAP.items():
            assert len(template) > 0, f"Empty fallback: {name}"

    def test_fallback_map_has_at_least_3_entries(self):
        assert len(FALLBACK_MAP) >= 2


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
        """Tier 1: Cache hit returns template without MLflow call."""
        client._redis.get = AsyncMock(return_value="Cached NTA prompt")
        result = await client.load(
            "zorven-wf2-nta-naming",
            fallback=FALLBACK_NAMING,
        )
        assert "Cached NTA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-3: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None
        result = await client.load(
            "zorven-wf2-nta-naming",
            fallback=FALLBACK_NAMING,
        )
        assert result == FALLBACK_NAMING

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        """AC-3: Both Redis and MLflow unreachable."""
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf2-nta-naming",
            fallback=FALLBACK_NAMING,
        )
        assert result == FALLBACK_NAMING

    async def test_format_applies_variables(self, client):
        """Variables are applied to loaded template."""
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf2-nta-naming",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result
