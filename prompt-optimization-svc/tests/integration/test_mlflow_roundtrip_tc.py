"""Integration tests for MLflow round-trip via testcontainers (US-059).

Tests prompt registration, versioning, state management, and template
loading against a real MLflow tracking server backed by testcontainer
PostgreSQL.
"""

import os

import pytest

from app.services.mlflow_registry import MLflowPromptRegistry

TEST_PREFIX = "__tc_mlflow_"


@pytest.mark.integration
class TestMLflowRoundtripTC:
    """MLflow prompt registry round-trip via testcontainers."""

    @pytest.fixture
    def registry(self):
        uri = os.environ.get("POI_MLFLOW_TRACKING_URI", "http://localhost:5000")
        return MLflowPromptRegistry(uri)

    def test_register_get_roundtrip(self, registry):
        """Register a prompt, retrieve it, verify template matches."""
        name = f"{TEST_PREFIX}roundtrip"
        info = registry.register_prompt(
            name=name,
            template="You are a helpful assistant for {{context.brand_name}}.",
            tags={"state": "DRAFT", "agent_code": "mra"},
        )
        assert info.name == name
        assert info.version >= 1

        retrieved = registry.get_prompt(name)
        assert retrieved is not None
        assert "helpful assistant" in retrieved.template

    def test_versioning_increments(self, registry):
        """Register same name twice — version increments."""
        name = f"{TEST_PREFIX}versioning"
        v1 = registry.register_prompt(name=name, template="Version 1")
        v2 = registry.register_prompt(name=name, template="Version 2")
        assert v2.version > v1.version

    def test_promote_sets_production_tag(self, registry):
        """Register, set state to PRODUCTION, verify promoted_at tag."""
        name = f"{TEST_PREFIX}promote"
        info = registry.register_prompt(
            name=name, template="Promote me", tags={"state": "DRAFT"}
        )
        registry.set_prompt_state(name, info.version, "PRODUCTION")

        promoted = registry.get_prompt_by_state(name, "PRODUCTION")
        assert promoted is not None
        assert promoted.tags.get("state") == "PRODUCTION"
        assert "promoted_at" in promoted.tags

    def test_load_prompt_template_resolves(self, registry):
        """Load template text by name."""
        name = f"{TEST_PREFIX}load"
        registry.register_prompt(name=name, template="Load me: {{context.x}}")
        template = registry.load_prompt_template(name)
        assert template is not None
        assert "Load me" in template

    def test_list_prompts_includes_registered(self, registry):
        """Listing includes newly registered prompt."""
        name = f"{TEST_PREFIX}list"
        registry.register_prompt(name=name, template="List me")
        names = registry.list_prompts()
        assert name in names

    def test_nonexistent_prompt_returns_none(self, registry):
        """Unknown prompt name returns None."""
        info = registry.get_prompt(f"{TEST_PREFIX}nonexistent-xyz-999")
        assert info is None
