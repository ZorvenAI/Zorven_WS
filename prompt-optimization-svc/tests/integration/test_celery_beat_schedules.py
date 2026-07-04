"""Integration tests for Celery Beat optimization schedules (US-046).

Validates Beat schedule configuration with real Celery app, and WF3
schedule behavior with real Redis tenant config.

Run with: pytest tests/integration/test_celery_beat_schedules.py -v -m integration
"""

import os

import pytest


def _redis_available() -> bool:
    """Check if Redis is reachable."""
    redis_url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "")
    if not redis_url:
        return False
    try:
        import redis

        r = redis.from_url(redis_url)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


def _mlflow_available() -> bool:
    """Check if MLflow is reachable."""
    mlflow_uri = os.environ.get("POI_MLFLOW_TRACKING_URI", "")
    if not mlflow_uri:
        return False
    try:
        import httpx

        resp = httpx.get(f"{mlflow_uri}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis not available (set POI_PROMPT_CACHE_REDIS_URL)",
)

requires_mlflow = pytest.mark.skipif(
    not _mlflow_available(),
    reason="MLflow not available (set POI_MLFLOW_TRACKING_URI)",
)


@pytest.mark.integration
class TestCeleryAppIntegration:
    """Celery app creates with all 6 §14.1 beat entries."""

    def test_celery_app_creates(self):
        from app.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "prompt_optimization"

    def test_beat_schedule_has_6_entries(self):
        from app.celery_app import celery_app

        assert len(celery_app.conf.beat_schedule) == 6

    def test_all_task_modules_importable(self):
        from app.tasks import (
            mine_golden_examples,
            optimize_wf1_pipeline,
            optimize_wf2_pipeline,
            optimize_wf3_creative_pipeline,
            optimize_wf3_optimization_loop,
            prompt_health_check,
        )

        assert mine_golden_examples is not None
        assert optimize_wf1_pipeline is not None
        assert optimize_wf2_pipeline is not None
        assert optimize_wf3_creative_pipeline is not None
        assert optimize_wf3_optimization_loop is not None
        assert prompt_health_check is not None


@pytest.mark.integration
class TestWf3ScheduleWithRedis:
    """WF3 tenant schedule config reads from Redis correctly."""

    @requires_redis
    @pytest.mark.asyncio
    async def test_set_and_get_schedule(self):
        """Set wf3_optimization_schedule in Redis and read it back."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import TenantConfigManager
        from app.core.config import settings

        cache = PromptCacheManager(settings.PROMPT_CACHE_REDIS_URL)
        mgr = TenantConfigManager(prompt_cache=cache)

        test_tenant = "test-us046-schedule"
        try:
            await mgr.set_optimization_schedule(test_tenant, "monthly")
            result = await mgr.get_optimization_schedule(test_tenant)
            assert result == "monthly"
        finally:
            # Cleanup
            r = await cache.connect()
            key = mgr.SCHEDULE_KEY.format(tenant_id=test_tenant)
            await r.delete(key)

    @requires_redis
    @pytest.mark.asyncio
    async def test_default_schedule_no_key(self):
        """No key in Redis returns default schedule."""
        from app.cache.prompt_cache import PromptCacheManager
        from app.cache.tenant_config import DEFAULT_SCHEDULE, TenantConfigManager
        from app.core.config import settings

        cache = PromptCacheManager(settings.PROMPT_CACHE_REDIS_URL)
        mgr = TenantConfigManager(prompt_cache=cache)

        result = await mgr.get_optimization_schedule("nonexistent-tenant-us046")
        assert result == DEFAULT_SCHEDULE


@pytest.mark.integration
class TestHealthCheckIntegration:
    """Health check task runs against real services."""

    @requires_mlflow
    def test_health_check_runs_no_crash(self):
        """Health check completes without error (may find 0 prompts)."""
        from app.tasks.prompt_health_check import prompt_health_check

        result = prompt_health_check()
        assert isinstance(result, dict)
        assert "checked" in result
        assert "healthy" in result
        assert "degraded" in result
        assert "reopt_triggered" in result

    @requires_mlflow
    def test_health_check_result_shape(self):
        """Health check returns all expected keys."""
        from app.tasks.prompt_health_check import prompt_health_check

        result = prompt_health_check()
        expected_keys = {
            "checked",
            "healthy",
            "degraded",
            "reopt_triggered",
            "not_loadable",
            "details",
        }
        assert expected_keys.issubset(result.keys())

    @requires_mlflow
    def test_health_check_counts_non_negative(self):
        """All count values are non-negative integers."""
        from app.tasks.prompt_health_check import prompt_health_check

        result = prompt_health_check()
        for key in [
            "checked",
            "healthy",
            "degraded",
            "reopt_triggered",
            "not_loadable",
        ]:
            assert isinstance(result[key], int)
            assert result[key] >= 0
