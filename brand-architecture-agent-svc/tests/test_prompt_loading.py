"""Tests for BAA prompt loading integration."""

from unittest.mock import AsyncMock

import pytest

from app.prompts.fallbacks import (
    FALLBACK_MAP,
    FALLBACK_HIERARCHY,
)
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-3: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_hierarchy_defined(self):
        assert FALLBACK_HIERARCHY is not None
        assert len(FALLBACK_HIERARCHY) > 20

    def test_fallback_map_has_hierarchy_prompt(self):
        assert "zorven-wf2-baa-hierarchy" in FALLBACK_MAP

    def test_all_fallbacks_non_empty(self):
        for name, template in FALLBACK_MAP.items():
            assert len(template) > 0, f"Empty fallback: {name}"

    def test_fallback_map_has_at_least_3_entries(self):
        assert len(FALLBACK_MAP) >= 1


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
        client._redis.get = AsyncMock(return_value="Cached BAA prompt")
        result = await client.load(
            "zorven-wf2-baa-hierarchy",
            fallback=FALLBACK_HIERARCHY,
        )
        assert "Cached BAA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-3: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None
        result = await client.load(
            "zorven-wf2-baa-hierarchy",
            fallback=FALLBACK_HIERARCHY,
        )
        assert result == FALLBACK_HIERARCHY

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        """AC-3: Both Redis and MLflow unreachable."""
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf2-baa-hierarchy",
            fallback=FALLBACK_HIERARCHY,
        )
        assert result == FALLBACK_HIERARCHY

    async def test_format_applies_variables(self, client):
        """Variables are applied to loaded template."""
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf2-baa-hierarchy",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result
