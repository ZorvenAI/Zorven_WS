"""Tests for health endpoint."""


async def test_health_returns_200(client):
    """GET /health should return 200 with service info."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "odoo-worker-agent-svc"


async def test_health_response_schema(client):
    """Health response should match HealthResponse schema."""
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert len(data) == 2
