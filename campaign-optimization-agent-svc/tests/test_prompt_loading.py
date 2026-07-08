"""Tests for COA prompt loading integration."""

import logging
from unittest.mock import AsyncMock

import pytest

from app.prompts.fallbacks import FALLBACK_MAP, FALLBACK_RECOMMENDATION, FALLBACK_REPORTER
from app.prompts.loader import AgentPromptClient


class TestFallbackPrompts:
    """AC-1: Each agent declares FALLBACK_PROMPT constants."""

    def test_fallback_recommendation_defined(self):
        assert FALLBACK_RECOMMENDATION is not None
        assert len(FALLBACK_RECOMMENDATION) > 20

    def test_fallback_map_has_recommendation_prompt(self):
        assert "zorven-wf3-coa-recommendation" in FALLBACK_MAP

    def test_fallback_reporter_defined(self):
        assert FALLBACK_REPORTER is not None
        assert len(FALLBACK_REPORTER) > 20

    def test_fallback_map_has_reporter_prompt(self):
        assert "zorven-wf3-coa-reporter" in FALLBACK_MAP


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
        client._redis.get = AsyncMock(return_value="Cached COA prompt")
        result = await client.load(
            "zorven-wf3-coa-recommendation",
            fallback=FALLBACK_RECOMMENDATION,
        )
        assert "Cached COA prompt" == result

    async def test_fallback_on_all_fail(self, client):
        """AC-1: Fallback used when cache + MLflow both fail."""
        client._redis.get = AsyncMock(return_value=None)
        client._http = None
        result = await client.load(
            "zorven-wf3-coa-recommendation",
            fallback=FALLBACK_RECOMMENDATION,
        )
        assert result == FALLBACK_RECOMMENDATION

    async def test_fallback_on_redis_and_mlflow_down(self, client):
        client._redis = None
        client._http = None
        result = await client.load(
            "zorven-wf3-coa-recommendation",
            fallback=FALLBACK_RECOMMENDATION,
        )
        assert result == FALLBACK_RECOMMENDATION

    async def test_format_applies_variables(self, client):
        client._redis.get = AsyncMock(
            return_value="Analyze {context.brand_name}"
        )
        result = await client.load(
            "zorven-wf3-coa-recommendation",
            variables={"context.brand_name": "TestBrand"},
        )
        assert "TestBrand" in result

class TestCriticalAgentWarning:
    """AC-2: CRITICAL agents surface HIGH-severity warning on fallback."""

    async def test_critical_fallback_logs_warning(self, caplog):
        """CRITICAL agent fallback must emit a WARNING-level log."""
        import logging

        client = AgentPromptClient(
            redis_url="redis://localhost:6379/2",
            mlflow_uri="",
            critical_agent=True,
            fallback_only=False,
        )
        client._redis = None
        client._http = None

        with caplog.at_level(logging.WARNING):
            result = await client.load(
                "zorven-wf3-coa-recommendation",
                fallback=FALLBACK_RECOMMENDATION,
            )

        assert result == FALLBACK_RECOMMENDATION
        warnings = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and "CRITICAL AGENT FALLBACK" in r.message
        ]
        assert len(warnings) >= 1, (
            f"Expected CRITICAL AGENT FALLBACK warning, got: "
            f"{[r.message for r in caplog.records]}"
        )
