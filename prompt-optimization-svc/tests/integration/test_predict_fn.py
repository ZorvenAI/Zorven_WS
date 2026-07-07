"""Integration tests for make_predict_fn (US-018).

Requires real MLflow and Anthropic API key.
"""

import os

import pytest

from app.predict_fns.factory import make_predict_fn

from .conftest import MLFLOW_URI, requires_mlflow

ANTHROPIC_API_KEY = os.environ.get("POI_ANTHROPIC_API_KEY", "")

requires_anthropic = pytest.mark.skipif(
    not ANTHROPIC_API_KEY,
    reason="POI_ANTHROPIC_API_KEY not set",
)


@pytest.mark.integration
@requires_mlflow
class TestPredictFnWithRealMLflow:
    """Test factory with real MLflow prompt registry."""

    def test_factory_creates_callable(self):
        fn = make_predict_fn(
            "zorven-wf1-mra-system",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY or "placeholder",
        )
        assert callable(fn)
        assert fn.prompt_name == "zorven-wf1-mra-system"

    def test_missing_prompt_returns_empty(self):
        """Nonexistent prompt returns empty string."""
        fn = make_predict_fn(
            "__inttest_nonexistent_xyz",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY or "placeholder",
        )
        result = fn()
        assert result == ""


@pytest.mark.integration
@requires_mlflow
@requires_anthropic
class TestPredictFnEndToEnd:
    """End-to-end: real MLflow prompt → real Anthropic → text response."""

    @pytest.fixture
    def registry(self):
        from app.services.mlflow_registry import MLflowPromptRegistry

        return MLflowPromptRegistry(MLFLOW_URI)

    def test_end_to_end_with_registered_prompt(self, registry):
        """Register a prompt, create predict_fn, get real Claude response."""
        name = "__inttest_predict_fn_e2e"
        registry.register_prompt(
            name=name,
            template="Say hello to {{context.name}} in one sentence.",
        )

        fn = make_predict_fn(
            name,
            model="claude-haiku-4-5-20251001",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=50,
        )
        result = fn(context_name="World")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_cga_prompt_returns_text(self, registry):
        """AC-4: Factory works with CGA prompt."""
        name = "__inttest_predict_cga"
        registry.register_prompt(
            name=name,
            template="List one Meta Ads headline for {{context.brand_name}}.",
        )

        fn = make_predict_fn(
            name,
            model="claude-haiku-4-5-20251001",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=50,
        )
        result = fn(context_brand_name="TestBrand")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_mra_prompt_returns_text(self, registry):
        """AC-4: Factory works with MRA prompt."""
        name = "__inttest_predict_mra"
        registry.register_prompt(
            name=name,
            template="Name one trend in the {{context.industry}} industry.",
        )

        fn = make_predict_fn(
            name,
            model="claude-haiku-4-5-20251001",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=50,
        )
        result = fn(context_industry="tech")

        assert isinstance(result, str)
        assert len(result) > 0
