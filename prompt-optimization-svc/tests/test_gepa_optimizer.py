"""Tests for ZorvenGepaOptimizer (US-017)."""

from app.registries.optimization_budgets import (
    AGENT_BUDGETS,
    DEFAULT_BUDGET,
    get_budget,
)
from app.services.gepa_optimizer import OptimizationResult, ZorvenGepaOptimizer
from .conftest import MLFLOW_URI


class TestOptimizationBudgets:
    def test_cga_budget_is_500(self):
        assert get_budget("cga") == 500

    def test_caa_budget_is_400(self):
        assert get_budget("caa") == 400

    def test_adpub_budget_is_300(self):
        assert get_budget("adpub") == 300

    def test_coa_budget_is_300(self):
        assert get_budget("coa") == 300

    def test_bpa_budget_is_300(self):
        assert get_budget("bpa") == 300

    def test_mra_budget_is_200(self):
        assert get_budget("mra") == 200

    def test_unknown_gets_default(self):
        assert get_budget("x") == DEFAULT_BUDGET

    def test_case_insensitive(self):
        assert get_budget("CGA") == 500

    def test_all_15_agents(self):
        assert len(AGENT_BUDGETS) == 15

    def test_all_positive(self):
        for a, b in AGENT_BUDGETS.items():
            assert b > 0, f"{a} budget must be positive"


class TestZorvenGepaOptimizerConfig:
    def test_default_reflection_model(self):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)
        assert opt.reflection_model == "anthropic/claude-sonnet-4-6"

    def test_custom_reflection_model(self):
        opt = ZorvenGepaOptimizer(
            reflection_model="anthropic/claude-haiku-4-5",
            mlflow_tracking_uri=MLFLOW_URI,
        )
        assert opt.reflection_model == "anthropic/claude-haiku-4-5"

    def test_custom_mlflow_uri(self):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri="http://custom:5000")
        assert opt.mlflow_tracking_uri == "http://custom:5000"


class TestOptimize:
    def test_error_returns_result_with_error(self):
        """Errors return result with error message."""

        def bad_predict(**kwargs):
            raise RuntimeError("Intentional test error")

        opt = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)
        result = opt.optimize(
            prompt_uris=["prompts:/__test_gepa_nonexistent/1"],
            predict_fn=bad_predict,
            train_data=[],
            scorers=[],
            agent_code="mra",
        )
        assert result.error is not None
        assert result.agent_code == "mra"


class TestOptimizationResult:
    def test_defaults(self):
        r = OptimizationResult()
        assert r.best_prompt == ""
        assert r.best_score == 0.0
        assert r.budget_exhausted is False
        assert r.error is None

    def test_budget_exhausted(self):
        r = OptimizationResult(candidates_evaluated=500, budget_exhausted=True)
        assert r.budget_exhausted is True

    def test_error_state(self):
        r = OptimizationResult(error="Connection refused")
        assert r.error == "Connection refused"
