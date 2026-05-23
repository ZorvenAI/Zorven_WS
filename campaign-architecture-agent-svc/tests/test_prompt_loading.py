"""Tests for CAA prompt loading integration."""

import logging
from unittest.mock import AsyncMock

import pytest

from app.prompts.fallbacks import CRITICAL_AGENT, FALLBACK_MAP, FALLBACK_SYSTEM
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-1: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_system_defined(self):
        assert FALLBACK_SYSTEM is not None
        assert len(FALLBACK_SYSTEM) > 20

    def test_fallback_map_has_system_prompt(self):
        assert "zorven-wf3-caa-system" in FALLBACK_MAP

    def test_all_fallbacks_non_empty(self):
        for name, template in FALLBACK_MAP.items():
            assert len(template) > 0, f"Empty fallback: {name}"

    def test_fallback_map_has_at_least_3_entries(self):
        assert len(FALLBACK_MAP) >= 3

    def test_critical_agent_flag(self):
        """AC-2: CRITICAL agents flagged for HIGH-severity warnings."""
        assert CRITICAL_AGENT is False


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
        client._redis.get = AsyncMock(return_value="Cached CAA prompt")
        result = await client.load(
            "zorven-wf3-caa-system",
            fallback=FALLBACK_SYSTEM,
        )
        assert "Cached CAA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-1: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None
        result = await client.load(
            "zorven-wf3-caa-system",
            fallback=FALLBACK_SYSTEM,
        )
        assert result == FALLBACK_SYSTEM

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf3-caa-system",
            fallback=FALLBACK_SYSTEM,
        )
        assert result == FALLBACK_SYSTEM

    async def test_format_applies_variables(self, client):
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf3-caa-system",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result
