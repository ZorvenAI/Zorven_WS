"""Tests for the health endpoint."""


class TestHealth:
    async def test_health_returns_ok(self, client):
        """Health endpoint returns 200 with service name."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "audience-persona-agent"

    async def test_health_no_auth_required(self, client):
        """Health endpoint does not require authentication."""
        response = await client.get("/health")
        assert response.status_code == 200
