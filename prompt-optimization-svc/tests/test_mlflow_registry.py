"""Tests for MLflow Prompt Registry client using real MLflow (US-007, US-008)."""

import pytest

from app.services.mlflow_registry import MLflowPromptRegistry, PromptInfo
from .conftest import MLFLOW_URI, requires_mlflow

TEST_PREFIX = "__test_reg_"


@requires_mlflow
class TestRegisterPrompt:
    @pytest.fixture
    def registry(self):
        return MLflowPromptRegistry(MLFLOW_URI)

    def test_register_new_prompt(self, registry):
        info = registry.register_prompt(
            name=f"{TEST_PREFIX}new",
            template="You are a test assistant",
            tags={"state": "DRAFT"},
        )
        assert info.name == f"{TEST_PREFIX}new"
        assert info.version >= 1

    def test_register_with_tags(self, registry):
        tags = {"workflow": "wf1", "agent_code": "mra", "state": "DRAFT"}
        info = registry.register_prompt(
            f"{TEST_PREFIX}tags", "template", tags=tags
        )
        assert info.tags == tags


@requires_mlflow
class TestGetPrompt:
    @pytest.fixture
    def registry(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(
            name=f"{TEST_PREFIX}get",
            template="Get test template",
            tags={"state": "DRAFT"},
        )
        return reg

    def test_get_existing_prompt(self, registry):
        info = registry.get_prompt(f"{TEST_PREFIX}get")
        assert info is not None
        assert info.template == "Get test template"

    def test_get_nonexistent_prompt(self, registry):
        info = registry.get_prompt(f"{TEST_PREFIX}nonexistent_xyz")
        assert info is None


@requires_mlflow
class TestPromptExists:
    @pytest.fixture
    def registry(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(name=f"{TEST_PREFIX}exists", template="t")
        return reg

    def test_exists_true(self, registry):
        assert registry.prompt_exists(f"{TEST_PREFIX}exists") is True

    def test_exists_false(self, registry):
        assert registry.prompt_exists(f"{TEST_PREFIX}nope_xyz") is False


@requires_mlflow
class TestLoadPromptTemplate:
    @pytest.fixture
    def registry(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(
            name=f"{TEST_PREFIX}load",
            template="You are a {{context.role}}...",
        )
        return reg

    def test_load_latest_version(self, registry):
        template = registry.load_prompt_template(f"{TEST_PREFIX}load")
        assert template is not None
        assert "{{context.role}}" in template

    def test_load_nonexistent_returns_none(self, registry):
        template = registry.load_prompt_template(f"{TEST_PREFIX}nope_xyz")
        assert template is None


@requires_mlflow
class TestListPrompts:
    @pytest.fixture
    def registry(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(name=f"{TEST_PREFIX}list", template="listed")
        return reg

    def test_list_returns_names(self, registry):
        names = registry.list_prompts()
        assert f"{TEST_PREFIX}list" in names
