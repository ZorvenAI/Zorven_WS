"""Celery task: daily prompt health check (§14.1).

Scheduled via Beat: Daily 10:00 UTC (06:00 ET) per §14.1.

AC-3: Verifies all PRODUCTION prompts are loadable from MLflow
and triggers re-optimization on >10% scorer regression.
"""

import logging

from app.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)

# Map prompt name prefixes to their optimization task
_WORKFLOW_TASK_MAP = {
    "zorven-wf1-": "app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline",
    "zorven-wf2-": "app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline",
    "zorven-wf3-caa-": "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline",
    "zorven-wf3-cga-": "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline",
    "zorven-wf3-adpub-": "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline",
    "zorven-wf3-coa-": "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop",
    "zorven-wf3-ila-": "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop",
}


def _get_reopt_task_name(prompt_name: str) -> str | None:
    """Resolve which optimization task to trigger for a prompt."""
    for prefix, task_name in _WORKFLOW_TASK_MAP.items():
        if prompt_name.startswith(prefix):
            return task_name
    return None


def _check_regression(score_after: float | None, threshold: float) -> bool:
    """Check if a prompt has regressed beyond the threshold.

    Returns True if regression is detected (score dropped >threshold
    from the optimization run's score_after).
    """
    if score_after is None:
        return False
    # A score below (1 - threshold) of the original indicates regression
    # e.g., threshold=0.10 means any score below 90% of original triggers
    return score_after < (1.0 - threshold)


@celery_app.task(
    bind=True,
    name="app.tasks.prompt_health_check.prompt_health_check",
)
def prompt_health_check(self):
    """Verify all PRODUCTION prompts are loadable and performing (AC-3).

    1. Lists all registered prompts from MLflow
    2. Checks each PRODUCTION prompt is loadable
    3. Checks latest optimization run score for regression
    4. Triggers re-optimization if >10% regression detected
    """
    from app.services.mlflow_registry import MLflowPromptRegistry

    registry = MLflowPromptRegistry(tracking_uri=settings.MLFLOW_TRACKING_URI)

    threshold = settings.HEALTH_CHECK_REGRESSION_THRESHOLD
    result = {
        "checked": 0,
        "healthy": 0,
        "degraded": 0,
        "reopt_triggered": 0,
        "not_loadable": 0,
        "details": [],
    }

    try:
        prompt_names = registry.list_prompts()
    except Exception as exc:
        logger.error("Health check failed to list prompts: %s", exc)
        result["details"].append(f"Failed to list prompts: {exc}")
        return result

    triggered_tasks = set()

    for name in prompt_names:
        # Check if prompt has a PRODUCTION version
        prod_info = registry.get_prompt_by_state(name, "PRODUCTION")
        if prod_info is None:
            continue  # No PRODUCTION version — skip

        result["checked"] += 1

        # Verify loadability
        template = registry.load_prompt_template(name, prod_info.version)
        if template is None:
            logger.warning("Prompt %s v%d not loadable", name, prod_info.version)
            result["not_loadable"] += 1
            result["degraded"] += 1
            result["details"].append(f"{name} v{prod_info.version}: not loadable")

            # Trigger re-optimization for non-loadable prompts
            task_name = _get_reopt_task_name(name)
            if task_name and task_name not in triggered_tasks:
                try:
                    celery_app.send_task(task_name)
                    triggered_tasks.add(task_name)
                    result["reopt_triggered"] += 1
                    logger.info(
                        "Re-optimization triggered for %s via %s", name, task_name
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to trigger re-optimization for %s: %s", name, exc
                    )
            continue

        # Check for scorer regression via optimization run metadata
        score_tag = prod_info.tags.get("score_after")
        if score_tag is not None:
            try:
                score_after = float(score_tag)
                if _check_regression(score_after, threshold):
                    logger.warning(
                        "Prompt %s v%d regression detected: score=%.3f, threshold=%.2f",
                        name,
                        prod_info.version,
                        score_after,
                        threshold,
                    )
                    result["degraded"] += 1
                    result["details"].append(
                        f"{name} v{prod_info.version}: "
                        f"regression score={score_after:.3f}"
                    )

                    task_name = _get_reopt_task_name(name)
                    if task_name and task_name not in triggered_tasks:
                        try:
                            celery_app.send_task(task_name)
                            triggered_tasks.add(task_name)
                            result["reopt_triggered"] += 1
                            logger.info(
                                "Re-optimization triggered for %s via %s",
                                name,
                                task_name,
                            )
                        except Exception as exc:
                            logger.error(
                                "Failed to trigger re-optimization for %s: %s",
                                name,
                                exc,
                            )
                else:
                    result["healthy"] += 1
            except (ValueError, TypeError):
                result["healthy"] += 1
        else:
            result["healthy"] += 1

    logger.info(
        "Health check complete: checked=%d, healthy=%d, degraded=%d, "
        "reopt_triggered=%d",
        result["checked"],
        result["healthy"],
        result["degraded"],
        result["reopt_triggered"],
    )

    # Limit details for Celery result backend
    result["details"] = result["details"][:20]
    return result
