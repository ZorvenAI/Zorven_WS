"""Integration tests for health endpoint (US-002, US-004).

Requires real Redis and MLflow.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from .conftest import requires_mlflow, requires_redis


@pytest.mark.integration
@requires_redis
@requires_mlflow
class TestHealthEndpointIntegration:
    """US-002 AC-4: Health endpoint reports real dependency status."""

    @pytest.fixture
    async def client(self):
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as c:
            yield c

    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_health_reports_dependency_status(self, client):
        resp = await client.get("/health")
        data = resp.json()
        assert "dependencies" in data
        dep_names = [d["name"] for d in data["dependencies"]]
        assert "redis" in dep_names
        assert "mlflow" in dep_names
