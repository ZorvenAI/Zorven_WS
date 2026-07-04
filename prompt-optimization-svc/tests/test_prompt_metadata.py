"""Tests for prompt metadata (§3.4) and GET endpoints (US-009)."""

import pytest

from app.api.schemas import PromptMetadata
from app.registries.prompt_catalog import (
    AGENT_PORTS,
    OPTIMIZATION_GROUPS,
    PROMPT_CATALOG,
)


class TestPromptMetadataModel:
    def test_all_required_fields(self):
        m = PromptMetadata(
            workflow="wf1", agent_code="mra", agent_port=8021,
            skill="landscape", optimization_group="wf1-discovery-pipeline",
        )
        assert m.agent_port == 8021
        assert m.optimization_priority == "MEDIUM"
        assert m.last_optimized is None

    def test_all_fields_populated(self):
        m = PromptMetadata(
            workflow="wf3", agent_code="coa", agent_port=8044,
            skill="optimization", optimization_group="wf3-campaign-pipeline",
            tenant_overridable=False, optimization_priority="CRITICAL",
            last_optimized="2026-05-22T10:00:00Z", optimization_run_id="run-abc",
        )
        assert m.optimization_priority == "CRITICAL"
        assert m.tenant_overridable is False


class TestCatalogMetadata:
    REQUIRED_TAG_KEYS = {
        "workflow", "agent_code", "agent_port", "skill", "prompt_type",
        "model_target", "optimization_group", "tenant_overridable",
        "optimization_priority", "last_optimized", "optimization_run_id", "state",
    }

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_entry_has_all_tags(self, entry):
        for key in self.REQUIRED_TAG_KEYS:
            assert key in entry.tags, f"{entry.name} missing tag: {key}"

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_agent_port_valid(self, entry):
        agent = entry.tags["agent_code"]
        expected = AGENT_PORTS.get(agent)
        assert entry.tags["agent_port"] == str(expected)

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_priority_valid(self, entry):
        assert entry.tags["optimization_priority"] in {
            "CRITICAL", "HIGH", "MEDIUM", "LOW"
        }

    def test_critical_agents(self):
        for entry in PROMPT_CATALOG:
            if entry.tags["agent_code"] in ("adpub", "coa"):
                assert entry.tags["optimization_priority"] == "CRITICAL"


class TestAgentPortRegistry:
    def test_all_15_agents(self):
        assert len(AGENT_PORTS) == 15

    def test_port_values(self):
        assert AGENT_PORTS["mra"] == 8021
        assert AGENT_PORTS["cga"] == 8042
        assert AGENT_PORTS["ila"] == 8045


class TestOptimizationGroups:
    def test_all_3_workflows(self):
        assert len(OPTIMIZATION_GROUPS) == 3
