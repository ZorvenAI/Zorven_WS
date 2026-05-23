"""Tests for ZorvenGepaOptimizer (US-017)."""

from unittest.mock import MagicMock, patch

from app.registries.optimization_budgets import (
    AGENT_BUDGETS,
    DEFAULT_BUDGET,
    get_budget,
)
from app.services.gepa_optimizer import OptimizationResult, ZorvenGepaOptimizer


# ------------------------------------------------------------------
# Optimization budgets (AC-1)
# ------------------------------------------------------------------


class TestOptimizationBudgets:
    """AC-1: max_metric_calls per agent matches §4.3 defaults."""

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

    def test_cia_budget_is_200(self):
        assert get_budget("cia") == 200

    def test_apa_budget_is_200(self):
        assert get_budget("apa") == 200

    def test_unknown_agent_gets_default(self):
        assert get_budget("unknown") == DEFAULT_BUDGET

    def test_case_insensitive(self):
        assert get_budget("CGA") == 500

    def test_all_15_agents_have_budgets(self):
        assert len(AGENT_BUDGETS) == 15

    def test_all_budgets_positive(self):
        for agent, budget in AGENT_BUDGETS.items():
            assert budget > 0, f"{agent} budget must be positive"


# ------------------------------------------------------------------
# ZorvenGepaOptimizer configuration
# ------------------------------------------------------------------


class TestZorvenGepaOptimizerConfig:
    """Test optimizer configuration defaults."""

    def test_default_reflection_model(self):
        opt = ZorvenGepaOptimizer()
        assert opt.reflection_model == "anthropic/claude-sonnet-4-6"

    def test_custom_reflection_model(self):
        opt = ZorvenGepaOptimizer(reflection_model="anthropic/claude-haiku-4-5")
        assert opt.reflection_model == "anthropic/claude-haiku-4-5"

    def test_mlflow_tracking_uri_from_settings(self):
        opt = ZorvenGepaOptimizer()
        assert "mlflow" in opt.mlflow_tracking_uri.lower() or "5000" in opt.mlflow_tracking_uri

    def test_custom_mlflow_uri(self):
        opt = ZorvenGepaOptimizer(mlflow_tracking_uri="http://custom:5000")
        assert opt.mlflow_tracking_uri == "http://custom:5000"


# ------------------------------------------------------------------
# Optimization execution
# ------------------------------------------------------------------


class TestOptimize:
    """Test optimization execution with mocked MLflow."""

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.genai.optimize.optimize_prompts")
    @patch(
        "mlflow.genai.optimize.optimizers.GepaPromptOptimizer"
    )
    def test_optimize_calls_gepa(
        self, mock_gepa_cls, mock_optimize, mock_set_uri
    ):
        """Optimization invokes GepaPromptOptimizer + optimize_prompts."""
        mock_result = MagicMock()
        mock_result.best_prompt = "Optimized prompt text"
        mock_result.best_score = 0.85
        mock_result.num_evaluations = 150
        mock_result.run_id = "run-abc-123"
        mock_optimize.return_value = mock_result

        opt = ZorvenGepaOptimizer()
        result = opt.optimize(
            prompt_uris=["prompts:/zorven-wf1-mra-system/1"],
            predict_fn=lambda **kwargs: "response",
            train_data=[{"inputs": {}, "outputs": {}}],
            scorers=[],
            agent_code="mra",
        )

        assert result.best_score == 0.85
        assert result.candidates_evaluated == 150
        assert result.mlflow_run_id == "run-abc-123"
        assert result.agent_code == "mra"
        mock_gepa_cls.assert_called_once()

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.genai.optimize.optimize_prompts")
    @patch(
        "mlflow.genai.optimize.optimizers.GepaPromptOptimizer"
    )
    def test_agent_budget_used_by_default(
        self, mock_gepa_cls, mock_optimize, mock_set_uri
    ):
        """AC-1: Agent-specific budget used when max_metric_calls not specified."""
        opt = ZorvenGepaOptimizer()
        opt.optimize(
            prompt_uris=["prompts:/test/1"],
            predict_fn=lambda **kwargs: "",
            train_data=[],
            scorers=[],
            agent_code="cga",
        )

        call_kwargs = mock_gepa_cls.call_args[1]
        assert call_kwargs["max_metric_calls"] == 500

    @patch("mlflow.set_tracking_uri")
    @patch("mlflow.genai.optimize.optimize_prompts")
    @patch(
        "mlflow.genai.optimize.optimizers.GepaPromptOptimizer"
    )
    def test_custom_budget_overrides_default(
        self, mock_gepa_cls, mock_optimize, mock_set_uri
    ):
        """Custom max_metric_calls overrides agent default."""
        opt = ZorvenGepaOptimizer()
        opt.optimize(
            prompt_uris=["prompts:/test/1"],
            predict_fn=lambda **kwargs: "",
            train_data=[],
            scorers=[],
            agent_code="cga",
            max_metric_calls=100,
        )

        call_kwargs = mock_gepa_cls.call_args[1]
        assert call_kwargs["max_metric_calls"] == 100

    @patch("mlflow.set_tracking_uri", side_effect=Exception("unreachable"))
    def test_error_returns_result_with_error(self, mock_set_uri):
        """AC-4: Errors return result with error message."""
        opt = ZorvenGepaOptimizer()
        result = opt.optimize(
            prompt_uris=["prompts:/test/1"],
            predict_fn=lambda **kwargs: "",
            train_data=[],
            scorers=[],
            agent_code="mra",
        )

        assert result.error is not None
        assert result.candidates_evaluated == 0
        assert result.agent_code == "mra"


# ------------------------------------------------------------------
# OptimizationResult
# ------------------------------------------------------------------


class TestOptimizationResult:
    """Test OptimizationResult dataclass."""

    def test_defaults(self):
        r = OptimizationResult()
        assert r.best_prompt == ""
        assert r.best_score == 0.0
        assert r.candidates_evaluated == 0
        assert r.budget_exhausted is False
        assert r.error is None

    def test_budget_exhausted_flag(self):
        r = OptimizationResult(
            candidates_evaluated=500,
            budget_exhausted=True,
            agent_code="cga",
        )
        assert r.budget_exhausted is True

    def test_error_state(self):
        r = OptimizationResult(error="Connection refused")
        assert r.error == "Connection refused"
        assert r.best_score == 0.0
