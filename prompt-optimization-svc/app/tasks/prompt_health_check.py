"""Celery task: daily prompt health check (§14.1, §17.2).

Scheduled via Beat: Daily 10:00 UTC (06:00 ET) per §14.1.

AC-3: Verifies all PRODUCTION prompts are loadable from MLflow
and triggers re-optimization on >10% scorer regression.

§17.2 Auto-rollback (US-050): When regression >15% is detected within
48 hours of promotion, automatically rolls back to the previous
ARCHIVED version and alerts ADMIN.

Regression detection checks two sources for score data:
1. MLflow prompt version tag 'score_after' (set by optimization pipeline
   when promoting candidates — becomes available in EPIC-6+)
2. OptimizationRun table: latest completed run's MLflow metrics

Until the optimization pipeline writes score_after tags, the health check
primarily validates prompt loadability and cacheability.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app
from app.core.config import settings
from app.metrics import AUTO_ROLLBACK_TOTAL

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


def _is_within_rollback_window(
    promoted_at_str: str | None,
    window_hours: int,
) -> bool:
    """Check if a prompt was promoted within the rollback window.

    Args:
        promoted_at_str: ISO-8601 timestamp of promotion (from MLflow tag).
        window_hours: Maximum hours since promotion for auto-rollback.

    Returns:
        True if promotion is within the window. False if None or invalid.
    """
    if promoted_at_str is None:
        return False
    try:
        promoted_at = datetime.fromisoformat(promoted_at_str)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        return promoted_at >= cutoff
    except (ValueError, TypeError):
        return False


def _find_previous_archived_version(
    registry,
    prompt_name: str,
    current_version: int,
) -> int | None:
    """Find the highest ARCHIVED version below current_version.

    Used to determine the rollback target for auto-rollback.
    """
    try:
        versions = registry.client.search_prompt_versions(prompt_name)
        archived = []
        for pv in versions:
            tags = pv.tags or {}
            if tags.get("state") == "ARCHIVED" and int(pv.version) < current_version:
                archived.append(int(pv.version))
        return max(archived) if archived else None
    except Exception as exc:
        logger.error(
            "Failed to find previous archived version for %s: %s",
            prompt_name,
            exc,
        )
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


def _get_latest_run_score(prompt_name: str) -> float | None:
    """Query the OptimizationRun table for the latest completed run's score.

    Falls back to None if no run exists or DB is unavailable.
    """

    async def _query():
        from sqlalchemy import select

        from app.models.database import async_session_factory
        from app.models.optimization_run import OptimizationRun

        try:
            async with async_session_factory() as session:
                stmt = (
                    select(OptimizationRun)
                    .where(
                        OptimizationRun.prompt_name == prompt_name,
                        OptimizationRun.state.in_(
                            ["PRODUCTION", "CANARY", "PROMOTING"]
                        ),
                    )
                    .order_by(OptimizationRun.updated_at.desc())
                    .limit(1)
                )
                row = (await session.execute(stmt)).scalar_one_or_none()
                if row is None or row.mlflow_run_id is None:
                    return None

                # Try to get score from MLflow run metrics
                from mlflow.tracking import MlflowClient

                client = MlflowClient(settings.MLFLOW_TRACKING_URI)
                run = client.get_run(row.mlflow_run_id)
                return run.data.metrics.get("score_after")
        except Exception as exc:
            logger.debug("Could not fetch run score for %s: %s", prompt_name, exc)
            return None

    try:
        return asyncio.run(_query())
    except Exception:
        return None


@celery_app.task(
    bind=True,
    name="app.tasks.prompt_health_check.prompt_health_check",
)
def prompt_health_check(self):
    """Verify all PRODUCTION prompts are loadable and performing (AC-3, §17.2).

    1. Lists all registered prompts from MLflow
    2. Checks each PRODUCTION prompt is loadable
    3. Checks score_after tag or OptimizationRun metrics for regression
    4. Auto-rollback if >15% regression within 48h of promotion (US-050)
    5. Triggers re-optimization if >10% regression detected
    """
    from app.services.mlflow_registry import MLflowPromptRegistry

    registry = MLflowPromptRegistry(tracking_uri=settings.MLFLOW_TRACKING_URI)

    threshold = settings.HEALTH_CHECK_REGRESSION_THRESHOLD
    auto_rollback_threshold = settings.AUTO_ROLLBACK_REGRESSION_THRESHOLD
    rollback_window_hours = settings.AUTO_ROLLBACK_WINDOW_HOURS
    result = {
        "checked": 0,
        "healthy": 0,
        "degraded": 0,
        "reopt_triggered": 0,
        "rollback_triggered": 0,
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

        # Check for scorer regression — try tag first, then DB/MLflow run
        score_after = None
        score_tag = prod_info.tags.get("score_after")
        if score_tag is not None:
            try:
                score_after = float(score_tag)
            except (ValueError, TypeError):
                pass

        if score_after is None:
            score_after = _get_latest_run_score(name)

        if score_after is not None and _check_regression(score_after, threshold):
            logger.warning(
                "Prompt %s v%d regression detected: score=%.3f, threshold=%.2f",
                name,
                prod_info.version,
                score_after,
                threshold,
            )
            result["degraded"] += 1
            result["details"].append(
                f"{name} v{prod_info.version}: regression score={score_after:.3f}"
            )

            # §17.2 Auto-rollback: >15% regression within 48h of promotion
            promoted_at_str = prod_info.tags.get("promoted_at")
            if _check_regression(
                score_after, auto_rollback_threshold
            ) and _is_within_rollback_window(promoted_at_str, rollback_window_hours):
                prev_version = _find_previous_archived_version(
                    registry, name, prod_info.version
                )
                if prev_version is not None:
                    try:
                        from app.cache.prompt_cache import PromptCacheManager
                        from app.logic.rollback_manager import rollback_to_version

                        async def _do_rollback():
                            cache_mgr = PromptCacheManager(
                                redis_url=settings.PROMPT_CACHE_REDIS_URL
                            )
                            await cache_mgr.connect()
                            try:
                                return await rollback_to_version(
                                    prompt_name=name,
                                    target_version=prev_version,
                                    mlflow_registry=registry,
                                    prompt_cache=cache_mgr,
                                )
                            finally:
                                await cache_mgr.close()

                        rb_result = asyncio.run(_do_rollback())
                        if rb_result.success:
                            logger.error(
                                "ADMIN ALERT: Auto-rollback triggered for "
                                "%s v%d → v%d (regression %.1f%% within "
                                "%dh of promotion)",
                                name,
                                prod_info.version,
                                prev_version,
                                (1.0 - score_after) * 100,
                                rollback_window_hours,
                            )
                            AUTO_ROLLBACK_TOTAL.labels(prompt_name=name).inc()
                            result["rollback_triggered"] += 1
                        else:
                            logger.error(
                                "ADMIN ALERT: Auto-rollback FAILED for " "%s: %s",
                                name,
                                rb_result.error,
                            )
                    except Exception as exc:
                        logger.error("Auto-rollback exception for %s: %s", name, exc)

            # Always trigger re-optimization for any regression >10%
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

    logger.info(
        "Health check complete: checked=%d, healthy=%d, degraded=%d, "
        "reopt_triggered=%d, rollback_triggered=%d",
        result["checked"],
        result["healthy"],
        result["degraded"],
        result["reopt_triggered"],
        result["rollback_triggered"],
    )

    # Limit details for Celery result backend
    result["details"] = result["details"][:20]
    return result
