"""Celery task: canary health check (every 15 minutes).

Scans for active canary deployments and:
1. Auto-promotes canaries that have expired with healthy metrics
2. Auto-rolls back canaries showing >5% regression
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.celery_app import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.canary_health_check.canary_health_check",
)
def canary_health_check(self):
    """Check all active canaries for expiration and regression."""

    async def _run():
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.canary_manager import CanaryManager
        from app.logic.lifecycle import PromptLifecycleManager
        from app.services.mlflow_registry import MLflowPromptRegistry

        result = {
            "checked": 0,
            "promoted": 0,
            "rolled_back": 0,
            "healthy": 0,
            "errors": 0,
            "details": [],
        }

        cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
        await cache.connect()

        try:
            registry = MLflowPromptRegistry(settings.MLFLOW_TRACKING_URI)
            lcm = PromptLifecycleManager(registry)
        except Exception as exc:
            logger.error("Canary health check: MLflow unavailable: %s", exc)
            result["errors"] += 1
            result["details"].append(f"MLflow unavailable: {exc}")
            await cache.close()
            return result

        mgr = CanaryManager(cache, lifecycle_manager=lcm)
        now = datetime.now(timezone.utc)

        try:
            canaries = await mgr.list_active_canaries()
            for state in canaries:
                result["checked"] += 1
                try:
                    if now >= state.expires_at:
                        # Canary has expired — check final metrics and promote
                        regression = await mgr.check_canary_regression(
                            state.prompt_name
                        )
                        if regression is None:
                            # No regression or no metrics — promote
                            await mgr.promote_canary(state.prompt_name)
                            result["promoted"] += 1
                            result["details"].append(
                                f"PROMOTED: {state.prompt_name} v{state.canary_version} "
                                f"(expired, healthy)"
                            )
                        else:
                            # Regression detected — already rolled back by
                            # check_canary_regression()
                            result["rolled_back"] += 1
                            result["details"].append(
                                f"ROLLED_BACK: {state.prompt_name} v{state.canary_version} "
                                f"(regression {regression:.1%})"
                            )
                    else:
                        # Still active — check for regression
                        regression = await mgr.check_canary_regression(
                            state.prompt_name
                        )
                        if regression is not None:
                            result["rolled_back"] += 1
                            result["details"].append(
                                f"ROLLED_BACK: {state.prompt_name} v{state.canary_version} "
                                f"(regression {regression:.1%})"
                            )
                        else:
                            result["healthy"] += 1
                except Exception as exc:
                    result["errors"] += 1
                    result["details"].append(f"ERROR: {state.prompt_name}: {exc}")
                    logger.error(
                        "Canary health check error for %s: %s",
                        state.prompt_name,
                        exc,
                    )
        finally:
            await cache.close()

        logger.info(
            "Canary health check: checked=%d, promoted=%d, rolled_back=%d, "
            "healthy=%d, errors=%d",
            result["checked"],
            result["promoted"],
            result["rolled_back"],
            result["healthy"],
            result["errors"],
        )
        result["details"] = result["details"][:20]
        return result

    return asyncio.run(_run())
