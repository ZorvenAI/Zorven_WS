"""Tests for health endpoint and HealthChecker using real services."""

import pytest
import redis.asyncio as aioredis

from app.api.schemas import DependencyStatus, HealthResponse
from app.services.health_checker import HealthChecker

from .conftest import MLFLOW_URI, REDIS_URL, requires_mlflow, requires_redis


@requires_redis
class TestHealthChecker:
    """Tests for HealthChecker with real Redis."""

    @pytest.fixture
    async def checker(self, monkeypatch):
        # Override settings so health checker uses test MLflow URI
        monkeypatch.setattr(
            "app.services.health_checker.settings.MLFLOW_TRACKING_URI",
            MLFLOW_URI,
        )
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        checker = HealthChecker(redis_client=r)
        yield checker
        await r.aclose()

    async def test_check_redis_up(self, checker):
        result = await checker.check_redis()
        assert result.status == "up"
        assert result.name == "redis"
        assert result.latency_ms is not None

    @requires_mlflow
    async def test_check_mlflow_up(self, checker):
        result = await checker.check_mlflow()
        assert result.status == "up"
        assert result.name == "mlflow"

    async def test_check_kafka_disabled(self, checker):
        result = await checker.check_kafka()
        assert result.status == "disabled"
        assert result.name == "kafka"

    @requires_mlflow
    async def test_check_all_healthy_or_degraded(self, checker):
        result = await checker.check_all()
        assert result.status in ("healthy", "degraded")
        assert len(result.dependencies) == 4

    async def test_check_all_has_redis_up(self, checker):
        result = await checker.check_all()
        redis_dep = next(
            d for d in result.dependencies if d.name == "redis"
        )
        assert redis_dep.status == "up"


class TestHealthResponse:
    """Test health response schema."""

    def test_healthy_response(self):
        resp = HealthResponse(status="healthy", dependencies=[])
        assert resp.status == "healthy"

    def test_response_with_deps(self):
        deps = [
            DependencyStatus(name="mlflow", status="up", latency_ms=10.0),
            DependencyStatus(name="redis", status="up", latency_ms=1.0),
            DependencyStatus(name="kafka", status="disabled"),
            DependencyStatus(
                name="postgres", status="down", message="err"
            ),
        ]
        resp = HealthResponse(status="degraded", dependencies=deps)
        assert resp.status == "degraded"
        assert len(resp.dependencies) == 4
