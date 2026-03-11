"""Integration tests for full execute flow — requires running Redis."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.integration


class TestFullExecuteFlow:
    """End-to-end tests with real Redis, mocked external APIs."""

    async def test_health_endpoint(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

    async def test_execute_returns_structured_response(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/execute",
                json={
                    "input_prompt": "What is the market size for cloud computing?",
                    "config": {"focus": "market_analysis,sizing"},
                },
                headers={"X-Tenant-ID": "integration-test"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "query" in data
            assert "findings" in data
            assert "sources" in data
            assert "confidence_score" in data
