"""Integration tests for MLflow Prompt Registry (US-007, US-008, US-009).

Requires real MLflow at POI_MLFLOW_TRACKING_URI (default http://localhost:5000).
"""

import pytest

from app.services.mlflow_registry import MLflowPromptRegistry

from .conftest import MLFLOW_URI, requires_mlflow

TEST_PREFIX = "__inttest_"


@pytest.mark.integration
@requires_mlflow
class TestMLflowPromptRegistration:
    """US-007: Register and retrieve prompts from real MLflow."""

    @pytest.fixture
    def registry(self):
        return MLflowPromptRegistry(MLFLOW_URI)

    def test_register_and_get_prompt(self, registry):
        """Register a prompt, then retrieve it."""
        name = f"{TEST_PREFIX}register-test"
        info = registry.register_prompt(
            name=name,
            template="You are a test assistant for {{context.brand_name}}",
            tags={"state": "DRAFT", "agent_code": "mra", "workflow": "wf1"},
        )
        assert info.name == name
        assert info.version >= 1

        retrieved = registry.get_prompt(name)
        assert retrieved is not None
        assert "test assistant" in retrieved.template

    def test_register_creates_new_version(self, registry):
        """Registering same name creates a new version."""
        name = f"{TEST_PREFIX}version-test"
        v1 = registry.register_prompt(name=name, template="Version 1")
        v2 = registry.register_prompt(name=name, template="Version 2")
        assert v2.version > v1.version

    def test_load_prompt_template(self, registry):
        """US-009 AC-2: load_prompt_template resolves template text."""
        name = f"{TEST_PREFIX}load-test"
        registry.register_prompt(name=name, template="Load me: {{context.x}}")
        template = registry.load_prompt_template(name)
        assert template is not None
        assert "Load me" in template

    def test_nonexistent_prompt_returns_none(self, registry):
        info = registry.get_prompt(f"{TEST_PREFIX}nonexistent-xyz")
        assert info is None

    def test_list_prompts_includes_registered(self, registry):
        """list_prompts returns registered prompt names."""
        name = f"{TEST_PREFIX}list-test"
        registry.register_prompt(name=name, template="Listed")
        names = registry.list_prompts()
        assert name in names


@pytest.mark.integration
@requires_mlflow
class TestMLflowStateManagement:
    """US-008: Prompt state management against real MLflow."""

    @pytest.fixture
    def registry(self):
        return MLflowPromptRegistry(MLFLOW_URI)

    def test_set_and_read_state_tag(self, registry):
        """Set state tag, then read it back."""
        name = f"{TEST_PREFIX}state-test"
        registry.register_prompt(
            name=name, template="State test", tags={"state": "DRAFT"}
        )
        registry.set_prompt_state(name, 1, "STAGING")

        info = registry.get_prompt(name)
        assert info is not None
        assert info.tags.get("state") == "STAGING"

    def test_get_prompt_by_state(self, registry):
        """Find a prompt version by state tag."""
        name = f"{TEST_PREFIX}by-state-test"
        registry.register_prompt(
            name=name, template="Production prompt",
            tags={"state": "PRODUCTION"},
        )
        found = registry.get_prompt_by_state(name, "PRODUCTION")
        assert found is not None
        assert "Production" in found.template

    def test_get_prompt_by_state_not_found(self, registry):
        """Non-matching state returns None."""
        name = f"{TEST_PREFIX}no-state-test"
        registry.register_prompt(
            name=name, template="Draft only", tags={"state": "DRAFT"}
        )
        found = registry.get_prompt_by_state(name, "PRODUCTION")
        assert found is None
