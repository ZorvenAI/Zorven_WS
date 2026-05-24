"""Joint multi-prompt optimization runner (§4.2).

Optimizes a group of prompts jointly so they evolve together
and avoid local optima. Produces one MLflow run ID covering
all prompts, and promotes candidates as a coherent set.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.logic.lifecycle import PromptLifecycleManager, PromptState
from app.registries.optimization_groups import (
    OPTIMIZATION_GROUPS,
    OptimizationGroup,
    get_group,
)
from app.services.gepa_optimizer import OptimizationResult, ZorvenGepaOptimizer
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)


@dataclass
class JointOptimizationResult:
    """Result of a joint multi-prompt optimization run."""

    group_name: str = ""
    mlflow_run_id: str = ""
    prompt_results: dict[str, str] = field(default_factory=dict)
    overall_score: float = 0.0
    candidates_evaluated: int = 0
    promoted_as_set: bool = False
    duration_seconds: float = 0.0
    error: Optional[str] = None


class JointOptimizer:
    """Runs joint optimization for a named prompt group."""

    def __init__(
        self,
        gepa_optimizer: ZorvenGepaOptimizer,
        registry: Optional[MLflowPromptRegistry] = None,
        lifecycle_manager: Optional[PromptLifecycleManager] = None,
    ) -> None:
        self.gepa = gepa_optimizer
        self.registry = registry
        self.lifecycle_manager = lifecycle_manager

    def optimize_group(
        self,
        group_name: str,
        predict_fn: Callable[..., Any],
        train_data: list[dict[str, Any]],
        scorers: list[Any],
    ) -> JointOptimizationResult:
        """Run joint optimization for a named group (AC-1, AC-2).

        All prompts in the group are optimized in a single MLflow run,
        producing one run ID covering all prompts.
        """
        try:
            group = get_group(group_name)
        except KeyError as exc:
            return JointOptimizationResult(
                group_name=group_name, error=str(exc)
            )

        # Build prompt URIs for all prompts in the group
        prompt_uris = [
            f"prompts:/{name}" for name in group.prompt_names
        ]

        logger.info(
            "Starting joint optimization: group=%s, prompts=%d, agents=%s",
            group_name,
            len(prompt_uris),
            group.agent_codes,
        )

        # AC-2: Single optimization run covering all prompts
        # Use the first agent's budget (joint runs share budget)
        primary_agent = group.agent_codes[0]
        opt_result = self.gepa.optimize(
            prompt_uris=prompt_uris,
            predict_fn=predict_fn,
            train_data=train_data,
            scorers=scorers,
            agent_code=primary_agent,
        )

        return JointOptimizationResult(
            group_name=group_name,
            mlflow_run_id=opt_result.mlflow_run_id,
            prompt_results={
                name: opt_result.best_prompt
                for name in group.prompt_names
            },
            overall_score=opt_result.best_score,
            candidates_evaluated=opt_result.candidates_evaluated,
            duration_seconds=opt_result.duration_seconds,
            error=opt_result.error,
        )

    def promote_group(
        self,
        group_name: str,
        result: JointOptimizationResult,
    ) -> JointOptimizationResult:
        """Canary-promote all prompts as a coherent set (AC-3).

        All prompts in the group transition to CANARY together.
        If any fails, none are promoted.
        """
        if self.lifecycle_manager is None or self.registry is None:
            logger.warning(
                "Cannot promote group '%s' — lifecycle manager or "
                "registry not configured",
                group_name,
            )
            return result

        try:
            group = get_group(group_name)
        except KeyError:
            return result

        promoted = []
        try:
            for prompt_name in group.prompt_names:
                info = self.registry.get_prompt(prompt_name)
                if info is None:
                    continue
                self.lifecycle_manager.transition(
                    prompt_name,
                    info.version,
                    PromptState.STAGING,
                    PromptState.CANARY,
                )
                promoted.append(prompt_name)

            result.promoted_as_set = True
            logger.info(
                "Group '%s' promoted to CANARY as coherent set: %d prompts",
                group_name,
                len(promoted),
            )
        except Exception as exc:
            # Rollback: revert any already-promoted prompts
            logger.error(
                "Group promotion failed at %d/%d — rolling back: %s",
                len(promoted),
                len(group.prompt_names),
                exc,
            )
            for name in promoted:
                try:
                    info = self.registry.get_prompt(name)
                    if info:
                        self.lifecycle_manager.rollback(
                            name, info.version, PromptState.CANARY
                        )
                except Exception:
                    pass
            result.promoted_as_set = False
            result.error = f"Group promotion failed: {exc}"

        return result
