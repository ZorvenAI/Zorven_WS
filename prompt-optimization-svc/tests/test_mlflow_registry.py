"""Tests for MLflow Prompt Registry client."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.mlflow_registry import MLflowPromptRegistry, PromptInfo


@pytest.fixture
def mock_client():
    """Mock MlflowClient."""
    return MagicMock()


@pytest.fixture
def registry(mock_client):
    """MLflowPromptRegistry with mocked client."""
    with patch("app.services.mlflow_registry.MlflowClient", return_value=mock_client):
        reg = MLflowPromptRegistry("http://localhost:5000")
    reg.client = mock_client
    return reg


class TestRegisterPrompt:
    """Test prompt registration."""

    def test_register_new_prompt(self, registry, mock_client):
        mock_pv = MagicMock()
        mock_pv.version = 1
        mock_client.register_prompt.return_value = mock_pv

        info = registry.register_prompt(
            name="zorven-wf1-mra-system",
            template="You are a market researcher...",
            tags={"state": "DRAFT"},
        )
        assert info.name == "zorven-wf1-mra-system"
        assert info.version == 1
        mock_client.register_prompt.assert_called_once()

    def test_register_with_tags(self, registry, mock_client):
        mock_pv = MagicMock()
        mock_pv.version = 1
        mock_client.register_prompt.return_value = mock_pv

        tags = {"workflow": "wf1", "agent_code": "mra", "state": "DRAFT"}
        registry.register_prompt("test", "template", tags=tags)
        call_kwargs = mock_client.register_prompt.call_args[1]
        assert call_kwargs["tags"] == tags


class TestGetPrompt:
    """Test prompt retrieval."""

    def test_get_existing_prompt(self, registry, mock_client):
        mock_prompt = MagicMock()
        mock_prompt.latest_version = 2
        mock_client.get_prompt.return_value = mock_prompt

        mock_pv = MagicMock()
        mock_pv.template = "Template text"
        mock_pv.tags = {"state": "DRAFT"}
        mock_client.get_prompt_version.return_value = mock_pv

        info = registry.get_prompt("zorven-wf1-mra-system")
        assert info is not None
        assert info.version == 2
        assert info.template == "Template text"

    def test_get_nonexistent_prompt(self, registry, mock_client):
        mock_client.get_prompt.side_effect = Exception("not found")
        info = registry.get_prompt("nonexistent")
        assert info is None


class TestPromptExists:
    """Test existence check."""

    def test_exists_true(self, registry, mock_client):
        mock_prompt = MagicMock()
        mock_prompt.latest_version = 1
        mock_client.get_prompt.return_value = mock_prompt
        mock_pv = MagicMock()
        mock_pv.template = "t"
        mock_pv.tags = {}
        mock_client.get_prompt_version.return_value = mock_pv

        assert registry.prompt_exists("zorven-wf1-mra-system") is True

    def test_exists_false(self, registry, mock_client):
        mock_client.get_prompt.side_effect = Exception("not found")
        assert registry.prompt_exists("nonexistent") is False


class TestLoadPromptTemplate:
    """Test template loading (AC-5 smoke test pattern)."""

    def test_load_latest_version(self, registry, mock_client):
        mock_prompt = MagicMock()
        mock_prompt.latest_version = 3
        mock_client.get_prompt.return_value = mock_prompt

        mock_pv = MagicMock()
        mock_pv.template = "You are a {{context.role}}..."
        mock_client.get_prompt_version.return_value = mock_pv

        template = registry.load_prompt_template("zorven-wf1-mra-system")
        assert template == "You are a {{context.role}}..."

    def test_load_specific_version(self, registry, mock_client):
        mock_pv = MagicMock()
        mock_pv.template = "Version 2 template"
        mock_client.get_prompt_version.return_value = mock_pv

        template = registry.load_prompt_template("test", version=2)
        assert template == "Version 2 template"
        mock_client.get_prompt_version.assert_called_once_with("test", 2)

    def test_load_nonexistent_returns_none(self, registry, mock_client):
        mock_client.get_prompt.side_effect = Exception("not found")
        template = registry.load_prompt_template("nonexistent")
        assert template is None


class TestListPrompts:
    """Test prompt listing."""

    def test_list_returns_names(self, registry, mock_client):
        mock_p1 = MagicMock()
        mock_p1.name = "zorven-wf1-mra-system"
        mock_p2 = MagicMock()
        mock_p2.name = "zorven-wf2-bpa-system"
        mock_client.search_prompts.return_value = [mock_p1, mock_p2]

        names = registry.list_prompts()
        assert names == ["zorven-wf1-mra-system", "zorven-wf2-bpa-system"]
