"""Celery task definitions for Campaign Optimization Agent.

Tasks delegate to the tick_executor for actual processing.
Celery tasks are synchronous; they run the async tick_executor
via asyncio.run().
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.run_optimization_tick",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def run_optimization_tick(
    self,
    campaign_age_min_days: int | None = None,
    campaign_age_max_days: int | None = None,
):
    """Run an optimization tick for campaigns within the specified age range.

    Args:
        campaign_age_min_days: Minimum campaign age in days (inclusive).
            None means no lower bound.
        campaign_age_max_days: Maximum campaign age in days (exclusive).
            None means no upper bound.
    """
    logger.info(
        "Optimization tick started: age_min=%s, age_max=%s",
        campaign_age_min_days,
        campaign_age_max_days,
    )
    try:
        from app.services.tick_executor import TickExecutor

        executor = TickExecutor()
        result = asyncio.run(
            executor.execute_tick(
                campaign_age_min_days=campaign_age_min_days,
                campaign_age_max_days=campaign_age_max_days,
            )
        )
        logger.info(
            "Optimization tick completed: %d campaigns processed, "
            "%d recommendations, %d actions executed",
            result.get("campaigns_processed", 0),
            result.get("recommendations_generated", 0),
            result.get("actions_executed", 0),
        )
        return result
    except Exception as exc:
        logger.error("Optimization tick failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.tasks.expire_stale_recommendations",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def expire_stale_recommendations(self):
    """Expire recommendations that have passed their 48h TTL.

    Scans pending recommendations and marks expired ones.
    """
    logger.info("Expiring stale recommendations")
    try:
        from app.services.approval_handler import ApprovalHandler

        handler = ApprovalHandler()
        count = asyncio.run(handler.expire_stale_recommendations())
        logger.info("Expired %d stale recommendations", count)
        return {"expired_count": count}
    except Exception as exc:
        logger.error(
            "Expire stale recommendations failed: %s", exc, exc_info=True
        )
        raise self.retry(exc=exc)
