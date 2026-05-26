"""Integration tests for context variable registry (US-031)."""

from app.registries.context_variables import (
    CONTEXT_REGISTRY,
    validate_template_against_registry,
)
from app.registries.prompt_catalog import PROMPT_CATALOG


class TestCatalogRegistryValidation:
    """All 48 catalog templates should pass registry validation."""

    def test_all_templates_pass_validation(self):
        for entry in PROMPT_CATALOG:
            agent_code = entry.tags.get("agent_code", "")
            violations = validate_template_against_registry(entry.template, agent_code)
            assert violations == [], (
                f"Template {entry.name} (agent={agent_code}) has "
                f"undeclared placeholders: {violations}"
            )

    def test_registry_loaded_at_import(self):
        assert len(CONTEXT_REGISTRY) >= 39

    def test_all_catalog_agents_in_registry(self):
        from app.registries.context_variables import get_variables_for_agent

        agents_seen = {entry.tags["agent_code"] for entry in PROMPT_CATALOG}
        for agent in agents_seen:
            vars_for = get_variables_for_agent(agent)
            assert (
                len(vars_for) >= 5
            ), f"Agent {agent} has too few variables: {len(vars_for)}"
