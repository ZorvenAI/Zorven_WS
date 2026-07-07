"""Celery task: mine golden examples from production optimization runs.

Scheduled via Beat: Saturdays 03:00 ET (07:00 UTC) per §14.1.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.mine_golden_examples.mine_golden_examples")
def mine_golden_examples(self, quality_threshold=0.8, lookback_days=7):
    """Mine high-quality optimization runs into golden datasets.

    This is a sync Celery task that wraps the async mining logic.
    Runs weekly via Beat schedule.
    """
    from app.datasets.miner import mine_completed_runs
    from app.models.database import async_session_factory

    logger.info(
        "Starting golden dataset mining: threshold=%.2f, lookback=%d days",
        quality_threshold,
        lookback_days,
    )

    result = asyncio.run(
        mine_completed_runs(
            session_factory=async_session_factory,
            quality_threshold=quality_threshold,
            lookback_days=lookback_days,
        )
    )

    logger.info(
        "Mining complete: %d mined, %d skipped, %d errors",
        result.mined,
        result.skipped,
        result.errors,
    )

    return {
        "mined": result.mined,
        "skipped": result.skipped,
        "errors": result.errors,
        "details": result.details[:20],  # Limit detail size for Celery result
    }
