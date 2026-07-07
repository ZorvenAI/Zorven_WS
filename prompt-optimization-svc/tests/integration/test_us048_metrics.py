"""Integration tests for Prometheus metrics (US-048).

Requires the FastAPI app to be importable and Prometheus client running.
"""

import pytest

from app.metrics import (
    MLFLOW_HEALTH,
    PROMPT_CACHE_HIT,
    PROMPT_FALLBACK_USAGE,
    PROMPT_LOAD_LATENCY,
    record_optimization_run,
    record_prompt_quality,
)


@pytest.mark.integration
class TestMetricsEndpointIntegration:
    def test_metrics_endpoint_returns_prometheus_text_format(self):
        from fastapi.testclient import TestClient

        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert resp.status_code == 200
        # Prometheus text format starts with HELP or TYPE comments
        assert "# HELP" in resp.text or "# TYPE" in resp.text

    def test_metrics_endpoint_contains_mlflow_health(self):
        from fastapi.testclient import TestClient

        from app.main import app

        # Set a value first so it appears in output
        MLFLOW_HEALTH.set(1.0)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert "poi_mlflow_server_health" in resp.text

    def test_metrics_endpoint_contains_prompt_cache_hit(self):
        from fastapi.testclient import TestClient

        from app.main import app

        # Ensure at least one sample exists
        PROMPT_CACHE_HIT.labels(tier="tier1_production", result="hit").inc(0)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert "poi_prompt_cache_hit_total" in resp.text

    def test_metrics_endpoint_contains_optimization_run_metrics(self):
        from fastapi.testclient import TestClient

        from app.main import app

        record_optimization_run("test-agent", "test-group", 10.0, 5.0)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert "poi_optimization_run_duration_seconds" in resp.text
        assert "poi_optimization_run_cost_usd" in resp.text

    def test_metrics_endpoint_contains_quality_gauges(self):
        from fastapi.testclient import TestClient

        from app.main import app

        record_prompt_quality("test-agent", "test-prompt", 5.0, 1.0)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/metrics")
        assert "poi_prompt_improvement_pct" in resp.text
        assert "poi_scorer_regression_pct" in resp.text


@pytest.mark.integration
class TestPromptLoaderMetricsIntegration:
    @pytest.mark.asyncio
    async def test_fallback_increments_counter(self):
        """Loading a missing prompt increments the fallback counter."""
        from app.cache.prompt_cache import PromptCacheManager

        from app.services.prompt_loader import ZorvenPromptLoader

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        await cache.connect()
        try:
            loader = ZorvenPromptLoader(prompt_cache=cache)
            before = PROMPT_FALLBACK_USAGE.labels(
                name="nonexistent-prompt-048"
            )._value.get()
            await loader.load(
                "nonexistent-prompt-048",
                fallback_template="fallback text",
            )
            after = PROMPT_FALLBACK_USAGE.labels(
                name="nonexistent-prompt-048"
            )._value.get()
            assert after - before == 1
        finally:
            await cache.close()

    @pytest.mark.asyncio
    async def test_cache_miss_increments_counter(self):
        """A cache miss on a non-cached prompt increments the miss counter."""
        from app.cache.prompt_cache import PromptCacheManager

        from app.services.prompt_loader import ZorvenPromptLoader

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        await cache.connect()
        try:
            loader = ZorvenPromptLoader(prompt_cache=cache)
            before = PROMPT_CACHE_HIT.labels(
                tier="tier1_production", result="miss"
            )._value.get()
            await loader.load(
                "missing-prompt-048-miss",
                fallback_template="fb",
            )
            after = PROMPT_CACHE_HIT.labels(
                tier="tier1_production", result="miss"
            )._value.get()
            assert after > before
        finally:
            await cache.close()

    @pytest.mark.asyncio
    async def test_cache_hit_increments_counter(self):
        """Prompt in Redis cache increments the hit counter."""
        from app.cache.prompt_cache import PromptCacheManager

        from app.services.prompt_loader import ZorvenPromptLoader

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        await cache.connect()
        try:
            # Pre-seed the cache
            await cache.set_prompt("cached-prompt-048", "Hello {name}", ttl=60)
            loader = ZorvenPromptLoader(prompt_cache=cache)
            before = PROMPT_CACHE_HIT.labels(
                tier="tier1_production", result="hit"
            )._value.get()
            result = await loader.load(
                "cached-prompt-048",
                variables={"name": "World"},
            )
            after = PROMPT_CACHE_HIT.labels(
                tier="tier1_production", result="hit"
            )._value.get()
            assert after > before
            assert result == "Hello World"
            # Clean up
            await cache.invalidate_prompt("cached-prompt-048")
        finally:
            await cache.close()

    @pytest.mark.asyncio
    async def test_latency_histogram_observed(self):
        """Prompt load observes the latency histogram."""
        from app.cache.prompt_cache import PromptCacheManager

        from app.services.prompt_loader import ZorvenPromptLoader

        cache = PromptCacheManager(redis_url="redis://localhost:6379/2")
        await cache.connect()
        try:
            loader = ZorvenPromptLoader(prompt_cache=cache)
            before = PROMPT_LOAD_LATENCY.labels(
                name="latency-test-048",
                tier="tier3_fallback",
                tenant_id="",
            )._sum.get()
            await loader.load(
                "latency-test-048",
                fallback_template="fb",
            )
            after = PROMPT_LOAD_LATENCY.labels(
                name="latency-test-048",
                tier="tier3_fallback",
                tenant_id="",
            )._sum.get()
            assert after > before
        finally:
            await cache.close()
