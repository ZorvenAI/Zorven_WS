"""Tests for health endpoint and HealthChecker."""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.schemas import DependencyStatus, HealthResponse
from app.services.health_checker import HealthChecker


class TestHealthChecker:
    """Unit tests for HealthChecker."""

    @pytest.fixture
    def checker(self):
        """HealthChecker with mocked Redis."""
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        return HealthChecker(redis_client=mock_redis)

    async def test_check_redis_up(self, checker):
        """Redis ping succeeds → status up."""
        result = await checker.check_redis()
        assert result.status == "up"
        assert result.name == "redis"
        assert result.latency_ms is not None

    async def test_check_redis_down(self):
        """Redis ping fails → status down."""
        mock_redis = AsyncMock()
        mock_redis.ping.side_effect = ConnectionError("refused")
        checker = HealthChecker(redis_client=mock_redis)
        result = await checker.check_redis()
        assert result.status == "down"
        assert result.name == "redis"

    @patch("app.services.health_checker.httpx.AsyncClient")
    async def test_check_mlflow_up(self, mock_client_cls, checker):
        """MLflow /health returns 200 → status up."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await checker.check_mlflow()
        assert result.status == "up"
        assert result.name == "mlflow"

    @patch("app.services.health_checker.httpx.AsyncClient")
    async def test_check_mlflow_down(self, mock_client_cls, checker):
        """MLflow unreachable → status down."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        result = await checker.check_mlflow()
        assert result.status == "down"
        assert result.name == "mlflow"

    async def test_check_kafka_disabled(self, checker):
        """Empty bootstrap servers → status disabled."""
        with patch("app.services.health_checker.settings") as mock_settings:
            mock_settings.KAFKA_BOOTSTRAP_SERVERS = ""
            result = await checker.check_kafka()
        assert result.status == "disabled"
        assert result.name == "kafka"

    @patch("app.services.health_checker.httpx.AsyncClient")
    async def test_check_all_healthy(self, mock_client_cls, checker):
        """All deps up → status healthy."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with (
            patch.object(checker, "check_kafka") as mock_kafka,
            patch.object(checker, "check_postgres") as mock_pg,
        ):
            mock_kafka.return_value = DependencyStatus(name="kafka", status="disabled")
            mock_pg.return_value = DependencyStatus(
                name="postgres", status="up", latency_ms=5.0
            )
            result = await checker.check_all()

        assert result.status == "healthy"
        assert len(result.dependencies) == 4

    @patch("app.services.health_checker.httpx.AsyncClient")
    async def test_check_all_unhealthy_when_mlflow_down(self, mock_client_cls, checker):
        """MLflow down → status unhealthy."""
        mock_client = AsyncMock()
        mock_client.get.side_effect = ConnectionError("refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with (
            patch.object(checker, "check_kafka") as mock_kafka,
            patch.object(checker, "check_postgres") as mock_pg,
        ):
            mock_kafka.return_value = DependencyStatus(name="kafka", status="disabled")
            mock_pg.return_value = DependencyStatus(
                name="postgres", status="up", latency_ms=5.0
            )
            result = await checker.check_all()

        assert result.status == "unhealthy"

    @patch("app.services.health_checker.httpx.AsyncClient")
    async def test_check_all_degraded_when_postgres_down(
        self, mock_client_cls, checker
    ):
        """Postgres down (optional) → status degraded."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        with (
            patch.object(checker, "check_kafka") as mock_kafka,
            patch.object(checker, "check_postgres") as mock_pg,
        ):
            mock_kafka.return_value = DependencyStatus(name="kafka", status="disabled")
            mock_pg.return_value = DependencyStatus(
                name="postgres", status="down", message="refused"
            )
            result = await checker.check_all()

        assert result.status == "degraded"


class TestHealthResponse:
    """Test health response schema."""

    def test_healthy_response(self):
        resp = HealthResponse(status="healthy", dependencies=[])
        assert resp.status == "healthy"
        assert resp.dependencies == []

    def test_response_with_deps(self):
        deps = [
            DependencyStatus(name="mlflow", status="up", latency_ms=10.0),
            DependencyStatus(name="redis", status="up", latency_ms=1.0),
            DependencyStatus(name="kafka", status="disabled"),
            DependencyStatus(name="postgres", status="down", message="err"),
        ]
        resp = HealthResponse(status="degraded", dependencies=deps)
        assert resp.status == "degraded"
        assert len(resp.dependencies) == 4
        assert resp.dependencies[2].latency_ms is None
        assert resp.dependencies[3].message == "err"
