"""Tests for APA prompt loading integration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.prompts.fallbacks import FALLBACK_MAP, FALLBACK_SYSTEM
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-2: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_system_defined(self):
        assert FALLBACK_SYSTEM is not None
        assert len(FALLBACK_SYSTEM) > 20

    def test_fallback_map_has_system_prompt(self):
        assert "zorven-wf1-apa-system" in FALLBACK_MAP

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
        )
        c._redis = AsyncMock()
        c._http = AsyncMock()
        return c

    async def test_cache_hit_returns_template(self, client):
        """Tier 1: Cache hit returns template without MLflow call."""
        client._redis.get = AsyncMock(return_value="Cached APA prompt")
        result = await client.load(
            "zorven-wf1-apa-system",
            fallback=FALLBACK_SYSTEM,
        )
        assert "Cached APA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-2: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None  # MLflow unavailable
        result = await client.load(
            "zorven-wf1-apa-system",
            fallback=FALLBACK_SYSTEM,
        )
        assert result == FALLBACK_SYSTEM

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        """AC-2: Both Redis and MLflow unreachable."""
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf1-apa-system",
            fallback=FALLBACK_SYSTEM,
        )
        assert result == FALLBACK_SYSTEM

    async def test_format_applies_variables(self, client):
        """Variables are applied to loaded template."""
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf1-apa-system",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result
