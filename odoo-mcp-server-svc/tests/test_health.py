"""Tests for health endpoint."""


class TestHealth:
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_health_response_fields(self, client):
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "odoo-mcp-server"
        assert data["version"] == "0.1.0"
        assert "odoo_connected" in data

    async def test_execute_returns_200(self, client, valid_execute_payload):
        response = await client.post(
            "/execute",
            json=valid_execute_payload,
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["tenant_id"] == "test-tenant"

    async def test_execute_extracts_skill_context(self, client, valid_execute_payload):
        response = await client.post(
            "/execute",
            json=valid_execute_payload,
            headers={"X-Tenant-ID": "test-tenant"},
        )
        data = response.json()
        assert data["data"]["skill_context_length"] > 0

    async def test_execute_empty_payload(self, client):
        response = await client.post(
            "/execute",
            json={},
            headers={"X-Tenant-ID": "default"},
        )
        assert response.status_code == 200
