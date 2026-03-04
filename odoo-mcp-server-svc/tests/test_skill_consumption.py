"""Tests for skill_context consumption from orchestrator config."""


class TestSkillConsumption:
    async def test_execute_extracts_skill_context(self, client):
        response = await client.post(
            "/execute",
            json={
                "input_prompt": "Search sales orders",
                "config": {"skill_context": "## Sales Pipeline\n- Use CRM module\n"},
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["skill_context_length"] > 0

    async def test_execute_empty_skill_context(self, client):
        response = await client.post(
            "/execute",
            json={
                "input_prompt": "Search",
                "config": {},
            },
            headers={"X-Tenant-ID": "test-tenant"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["skill_context_length"] == 0

    async def test_execute_no_config(self, client):
        response = await client.post(
            "/execute",
            json={"input_prompt": "Search"},
        )
        assert response.status_code == 200
