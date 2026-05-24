"""Tests for make_predict_fn factory using real MLflow + Anthropic (US-018)."""

import pytest

from app.predict_fns.factory import make_predict_fn
from app.services.mlflow_registry import MLflowPromptRegistry
from .conftest import ANTHROPIC_API_KEY, MLFLOW_URI, requires_mlflow

TEST_PREFIX = "__test_pfn_"


class TestMakePredictFnFactory:
    def test_factory_returns_callable(self):
        fn = make_predict_fn(
            "test", mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY or "placeholder",
        )
        assert callable(fn)

    def test_factory_attaches_metadata(self):
        fn = make_predict_fn(
            "zorven-wf1-mra-system", model="claude-haiku-4-5",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY or "placeholder",
        )
        assert fn.prompt_name == "zorven-wf1-mra-system"
        assert fn.model == "claude-haiku-4-5"

    def test_default_model(self):
        fn = make_predict_fn(
            "test", mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY or "placeholder",
        )
        assert fn.model == "claude-sonnet-4-6"
@requires_mlflow
class TestPredictFnExecution:
    def test_missing_prompt_returns_empty(self):
        fn = make_predict_fn(
            f"{TEST_PREFIX}nonexistent_xyz",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY or "placeholder",
        )
        result = fn()
        assert result == ""

    
    def test_registered_prompt_returns_text(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(
            name=f"{TEST_PREFIX}exec",
            template="Say hello in one word.",
        )
        fn = make_predict_fn(
            f"{TEST_PREFIX}exec",
            model="claude-haiku-4-5-20251001",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=10,
        )
        result = fn()
        assert isinstance(result, str)
        assert len(result) > 0
@requires_mlflow
class TestPredictFnAgentPrompts:
    def test_works_with_cga_prompt(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(
            name=f"{TEST_PREFIX}cga",
            template="List one ad headline for {{context.brand_name}}.",
        )
        fn = make_predict_fn(
            f"{TEST_PREFIX}cga",
            model="claude-haiku-4-5-20251001",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=30,
        )
        result = fn(context_brand_name="TestBrand")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_works_with_mra_prompt(self):
        reg = MLflowPromptRegistry(MLFLOW_URI)
        reg.register_prompt(
            name=f"{TEST_PREFIX}mra",
            template="Name one trend in {{context.industry}}.",
        )
        fn = make_predict_fn(
            f"{TEST_PREFIX}mra",
            model="claude-haiku-4-5-20251001",
            mlflow_tracking_uri=MLFLOW_URI,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=30,
        )
        result = fn(context_industry="tech")
        assert isinstance(result, str)
        assert len(result) > 0
