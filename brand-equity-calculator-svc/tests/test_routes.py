"""Tests for API routes."""


class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"


class TestCalculateEndpoint:
    async def test_returns_503_when_no_claude_client(self, client, valid_payload):
        """Without ANTHROPIC_API_KEY, the executor has no Claude client."""
        response = await client.post("/v1/calculate", json=valid_payload)
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

    async def test_missing_required_fields_returns_422(self, client):
        response = await client.post("/v1/calculate", json={"company_name": "Test"})
        assert response.status_code == 422

    async def test_empty_company_name_returns_422(self, client, valid_payload):
        valid_payload["company_name"] = ""
        response = await client.post("/v1/calculate", json=valid_payload)
        assert response.status_code == 422
