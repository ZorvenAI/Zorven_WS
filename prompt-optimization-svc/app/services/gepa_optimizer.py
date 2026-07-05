"""ZorvenGepaOptimizer — GEPA prompt optimization with Zorven defaults.

Wraps MLflow's GepaPromptOptimizer + optimize_prompts() with:
- reflection_model = claude-sonnet-4-6 (Anthropic)
- Per-agent max_metric_calls budgets (§4.3)
- Pareto frontier + minibatch sampling
- MLflow run tracking with traces
- Graceful budget exhaustion
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.core.config import settings
from app.registries.optimization_budgets import get_budget

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """Result of a GEPA optimization run."""

    best_prompt: str = ""
    best_score: float = 0.0
    candidates_evaluated: int = 0
    budget_exhausted: bool = False
    mlflow_run_id: str = ""
    duration_seconds: float = 0.0
    agent_code: str = ""
    prompt_uris: list[str] = field(default_factory=list)
    error: Optional[str] = None


class ZorvenGepaOptimizer:
    """GEPA prompt optimizer with Zorven-specific configuration.

    Uses MLflow's GepaPromptOptimizer with Anthropic Claude as the
    reflection model and per-agent budget limits.
    """

    DEFAULT_REFLECTION_MODEL = "anthropic/claude-sonnet-4-6"

    def __init__(
        self,
        reflection_model: Optional[str] = None,
        mlflow_tracking_uri: Optional[str] = None,
    ) -> None:
        self.reflection_model = reflection_model or self.DEFAULT_REFLECTION_MODEL
        self.mlflow_tracking_uri = mlflow_tracking_uri or settings.MLFLOW_TRACKING_URI

    def optimize(
        self,
        prompt_uris: list[str],
        predict_fn: Callable[..., Any],
        train_data: list[dict[str, Any]],
        scorers: list[Any],
        agent_code: str,
        max_metric_calls: Optional[int] = None,
        tenant_id: Optional[str] = None,
        gepa_kwargs: Optional[dict[str, Any]] = None,
    ) -> OptimizationResult:
        """Run a GEPA optimization with Zorven defaults.

        Args:
            prompt_uris: MLflow prompt URIs to optimize.
            predict_fn: Target function that uses the prompts.
            train_data: Evaluation dataset (inputs + expected outputs).
            scorers: List of MLflow scorers for evaluation.
            agent_code: Agent code for budget lookup (e.g., "cga").
            max_metric_calls: Override budget (None = use §4.3 default).
            tenant_id: Tenant ID for experiment namespacing (None = global).
            gepa_kwargs: Additional kwargs passed to GepaPromptOptimizer
                (e.g., task_description for reflection context enrichment).

        Returns:
            OptimizationResult with best candidate and run metadata.
        """
        budget = (
            max_metric_calls if max_metric_calls is not None else get_budget(agent_code)
        )
        start_time = time.monotonic()

        logger.info(
            "Starting GEPA optimization: agent=%s, prompts=%s, budget=%d, "
            "reflection_model=%s",
            agent_code,
            prompt_uris,
            budget,
            self.reflection_model,
        )

        # Track best candidate across potential partial failures
        best_prompt = ""
        best_score = 0.0
        candidates = 0
        run_id = ""

        try:
            import mlflow

            from app.logic.tenant_isolation import get_mlflow_experiment_name

            mlflow.set_tracking_uri(self.mlflow_tracking_uri)
            mlflow.set_experiment(get_mlflow_experiment_name(tenant_id))

            from mlflow.genai.optimize import optimize_prompts
            from mlflow.genai.optimize.optimizers import (
                GepaPromptOptimizer,
            )

            # Create GEPA optimizer with Zorven defaults (AC-2)
            gepa = GepaPromptOptimizer(
                reflection_model=self.reflection_model,
                max_metric_calls=budget,
                gepa_kwargs=gepa_kwargs,
            )

            # Run optimization with MLflow tracking (AC-3)
            result = optimize_prompts(
                predict_fn=predict_fn,
                train_data=train_data,
                prompt_uris=prompt_uris,
                optimizer=gepa,
                scorers=scorers,
                enable_tracking=True,
            )

            duration = time.monotonic() - start_time

            if result:
                best_prompt = getattr(result, "best_prompt", "")
                best_score = getattr(result, "best_score", 0.0)
                candidates = getattr(result, "num_evaluations", 0)
                run_id = getattr(result, "run_id", "")

            budget_exhausted = candidates >= budget

            logger.info(
                "GEPA optimization complete: agent=%s, score=%.3f, "
                "candidates=%d/%d, exhausted=%s, duration=%.1fs",
                agent_code,
                best_score,
                candidates,
                budget,
                budget_exhausted,
                duration,
            )

            return OptimizationResult(
                best_prompt=str(best_prompt),
                best_score=best_score,
                candidates_evaluated=candidates,
                budget_exhausted=budget_exhausted,
                mlflow_run_id=str(run_id),
                duration_seconds=round(duration, 2),
                agent_code=agent_code,
                prompt_uris=list(prompt_uris),
            )

        except Exception as exc:
            duration = time.monotonic() - start_time
            logger.exception(
                "GEPA optimization failed: agent=%s, duration=%.1fs",
                agent_code,
                duration,
            )
            # AC-4: Return best candidate found so far on failure
            return OptimizationResult(
                best_prompt=str(best_prompt) if best_prompt else "",
                best_score=best_score if best_score else 0.0,
                candidates_evaluated=candidates if candidates else 0,
                budget_exhausted=False,
                duration_seconds=round(duration, 2),
                agent_code=agent_code,
                prompt_uris=list(prompt_uris),
                error=str(exc),
            )
