"""Tests for prompt metadata (§3.4) and GET endpoints."""

import pytest

from app.api.schemas import PromptMetadata
from app.registries.prompt_catalog import (
    AGENT_PORTS,
    OPTIMIZATION_GROUPS,
    OPTIMIZATION_PRIORITY,
    PROMPT_CATALOG,
)


class TestPromptMetadataModel:
    """Test PromptMetadata Pydantic model (AC-1)."""

    def test_all_required_fields(self):
        """§3.4: metadata has all required fields."""
        m = PromptMetadata(
            workflow="wf1",
            agent_code="mra",
            agent_port=8021,
            skill="landscape",
            optimization_group="wf1-discovery-pipeline",
        )
        assert m.workflow == "wf1"
        assert m.agent_code == "mra"
        assert m.agent_port == 8021
        assert m.skill == "landscape"
        assert m.model_target == "claude-sonnet-4-6"
        assert m.optimization_group == "wf1-discovery-pipeline"
        assert m.tenant_overridable is True
        assert m.optimization_priority == "MEDIUM"
        assert m.last_optimized is None
        assert m.optimization_run_id is None

    def test_all_fields_populated(self):
        m = PromptMetadata(
            workflow="wf3",
            agent_code="coa",
            agent_port=8044,
            skill="optimization",
            model_target="claude-sonnet-4-6",
            optimization_group="wf3-campaign-pipeline",
            tenant_overridable=False,
            optimization_priority="CRITICAL",
            last_optimized="2026-05-22T10:00:00Z",
            optimization_run_id="run-abc-123",
        )
        assert m.optimization_priority == "CRITICAL"
        assert m.last_optimized == "2026-05-22T10:00:00Z"
        assert m.optimization_run_id == "run-abc-123"
        assert m.tenant_overridable is False


class TestCatalogMetadata:
    """Verify catalog entries have full §3.4 metadata tags (AC-1)."""

    REQUIRED_TAG_KEYS = {
        "workflow",
        "agent_code",
        "agent_port",
        "skill",
        "prompt_type",
        "model_target",
        "optimization_group",
        "tenant_overridable",
        "optimization_priority",
        "last_optimized",
        "optimization_run_id",
        "state",
    }

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_entry_has_all_metadata_tags(self, entry):
        """Each catalog entry has all §3.4 metadata fields as tags."""
        for key in self.REQUIRED_TAG_KEYS:
            assert key in entry.tags, f"{entry.name} missing tag: {key}"

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_agent_port_is_valid(self, entry):
        """agent_port tag matches the known port registry."""
        agent = entry.tags["agent_code"]
        expected_port = AGENT_PORTS.get(agent)
        assert entry.tags["agent_port"] == str(
            expected_port
        ), f"{entry.name}: port {entry.tags['agent_port']} != {expected_port}"

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_optimization_group_set(self, entry):
        """optimization_group tag is non-empty."""
        assert (
            entry.tags["optimization_group"] != ""
        ), f"{entry.name} missing optimization_group"

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_optimization_priority_valid(self, entry):
        """optimization_priority is one of CRITICAL/HIGH/MEDIUM/LOW."""
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        assert entry.tags["optimization_priority"] in valid

    def test_critical_agents_marked_critical(self):
        """ADPUB and COA should be CRITICAL priority."""
        for entry in PROMPT_CATALOG:
            if entry.tags["agent_code"] in ("adpub", "coa"):
                assert (
                    entry.tags["optimization_priority"] == "CRITICAL"
                ), f"{entry.name} should be CRITICAL"

    def test_model_target_set(self):
        """All entries have a model_target."""
        for entry in PROMPT_CATALOG:
            assert entry.tags["model_target"] != ""


class TestAgentPortRegistry:
    """Verify agent port mapping covers all 15 agents."""

    def test_all_15_agents_have_ports(self):
        assert len(AGENT_PORTS) == 15

    def test_port_values_are_correct(self):
        assert AGENT_PORTS["mra"] == 8021
        assert AGENT_PORTS["cga"] == 8042
        assert AGENT_PORTS["adpub"] == 8043
        assert AGENT_PORTS["ila"] == 8045


class TestOptimizationGroups:
    """Verify optimization group mapping."""

    def test_all_3_workflows_have_groups(self):
        assert len(OPTIMIZATION_GROUPS) == 3
        assert "wf1" in OPTIMIZATION_GROUPS[1]
        assert "wf2" in OPTIMIZATION_GROUPS[2]
        assert "wf3" in OPTIMIZATION_GROUPS[3]


# ------------------------------------------------------------------
# API endpoint tests for GET /v1/prompts and GET /v1/prompts/{name}
# ------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.services.mlflow_registry import PromptInfo


@pytest.fixture
async def client():
    """Async test client with mocked Redis."""
    with patch("app.cache.redis_manager.aioredis") as mock_aioredis:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.aclose.return_value = None
        mock_aioredis.from_url.return_value = mock_redis

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


class TestGetPromptDetailEndpoint:
    """Test GET /v1/prompts/{name} endpoint."""

    async def test_returns_503_when_not_initialized(self, client):
        """Registry not initialized → 503."""
        from app.api import routes

        routes.mlflow_registry = None
        resp = await client.get("/v1/prompts/zorven-wf1-mra-system")
        assert resp.status_code == 503

    async def test_returns_404_for_unknown_prompt(self, client):
        """Unknown prompt → 404."""
        from app.api import routes

        mock_reg = MagicMock()
        mock_reg.get_prompt.return_value = None
        routes.mlflow_registry = mock_reg

        resp = await client.get("/v1/prompts/zorven-wf1-mra-unknown")
        assert resp.status_code == 404

    async def test_returns_prompt_with_metadata(self, client):
        """Returns full detail with §3.4 metadata."""
        from app.api import routes

        mock_reg = MagicMock()
        mock_reg.get_prompt.return_value = PromptInfo(
            name="zorven-wf1-mra-system",
            version=1,
            template="You are a researcher...",
            tags={
                "workflow": "wf1",
                "agent_code": "mra",
                "agent_port": "8021",
                "skill": "system",
                "model_target": "claude-sonnet-4-6",
                "optimization_group": "wf1-discovery-pipeline",
                "tenant_overridable": "true",
                "optimization_priority": "MEDIUM",
                "last_optimized": "",
                "optimization_run_id": "",
                "state": "DRAFT",
            },
        )
        routes.mlflow_registry = mock_reg

        resp = await client.get("/v1/prompts/zorven-wf1-mra-system")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "zorven-wf1-mra-system"
        assert data["version"] == 1
        assert data["template"] == "You are a researcher..."
        assert data["metadata"]["agent_port"] == 8021
        assert data["metadata"]["optimization_group"] == "wf1-discovery-pipeline"


class TestListPromptsEndpoint:
    """Test GET /v1/prompts endpoint."""

    async def test_returns_503_when_not_initialized(self, client):
        from app.api import routes

        routes.mlflow_registry = None
        resp = await client.get("/v1/prompts")
        assert resp.status_code == 503

    async def test_returns_prompt_list(self, client):
        from app.api import routes

        mock_reg = MagicMock()
        mock_reg.list_prompts.return_value = ["zorven-wf1-mra-system"]
        mock_reg.get_prompt.return_value = PromptInfo(
            name="zorven-wf1-mra-system",
            version=1,
            template="t",
            tags={"state": "DRAFT", "agent_code": "mra", "workflow": "wf1"},
        )
        routes.mlflow_registry = mock_reg

        resp = await client.get("/v1/prompts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["prompts"][0]["name"] == "zorven-wf1-mra-system"
