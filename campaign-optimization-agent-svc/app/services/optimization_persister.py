"""SKL-COA-11: Optimization outcome persistence.

Persists tick results to Django backend via callbacks,
updates campaign registry, writes optimization history,
and updates performance cache.
"""

import logging
from typing import Any

from app.cache.redis_manager import RedisManager
from app.services.callback_client import CallbackClient

logger = logging.getLogger(__name__)


class OptimizationPersister:
    """Persists optimization outcomes to Django and Redis."""

    def __init__(
        self,
        callback_client: CallbackClient,
        redis_manager: RedisManager | None = None,
    ):
        self._callback = callback_client
        self._redis = redis_manager

    async def persist_tick_results(
        self,
        tenant_id: str,
        campaign_id: str,
        tick_results: dict[str, Any],
    ) -> None:
        """Persist all tick results.

        Args:
            tenant_id: Tenant identifier.
            campaign_id: Campaign identifier.
            tick_results: Full tick results payload including
                analysis, recommendations, execution results.
        """
        # 1. Bundle entity updates into the tick callback payload so the
        #    Django service-auth endpoint can apply them in a single call.
        entity_changes = tick_results.get("entity_changes", [])
        if entity_changes and "entity_updates" not in tick_results:
            tick_results["entity_updates"] = {
                "status": tick_results.get("campaign_status", "active"),
                "ad_sets": tick_results.get("ad_set_updates", []),
                "ads": tick_results.get("ad_updates", []),
            }

        # 2. Write optimization history via callback to Django.
        #    Recommendations + actions + entity_updates all flow through
        #    /optimization/callback/tick-result/ (X-Callback-Token auth).
        try:
            result = await self._callback.post_tick_result(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
                tick_results=tick_results,
            )
            if "error" in result:
                logger.warning(
                    "Tick result callback returned error: %s",
                    result["error"],
                )
        except Exception as exc:
            logger.error("Failed to post tick results: %s", exc)

        # 3. Update performance history cache
        if self._redis:
            try:
                perf_data = {
                    "metrics": tick_results.get("metrics", {}),
                    "health": tick_results.get("overall_health", ""),
                    "trends": tick_results.get("trends", {}),
                    "recommendations_count": tick_results.get(
                        "recommendations_generated", 0
                    ),
                    "actions_executed": tick_results.get(
                        "actions_executed", 0
                    ),
                }
                await self._redis.append_performance_history(
                    tenant_id=tenant_id,
                    campaign_id=campaign_id,
                    data=perf_data,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to update performance cache: %s", exc
                )

        # 4. Recommendation status updates are included in the tick
        #    callback payload (recommendations[].status) — Django persists
        #    them inside optimization_tick_callback. No separate PATCH.
        recommendations = tick_results.get("recommendations", [])

        logger.info(
            "Persisted tick results for campaign %s "
            "(tenant=%s, %d entity changes, %d recommendations)",
            campaign_id,
            tenant_id,
            len(entity_changes),
            len(recommendations),
        )
