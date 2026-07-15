"""Celery task: optimize WF1 discovery pipeline prompts.

Scheduled via Beat: Monthly, 2nd Sunday 06:00 UTC (02:00 ET) per §14.1.
Optimizes all WF1 agents (mra, cia, apa, tcia, voca) as a joint group.

Beat fires every Sunday; task self-guards for the 2nd Sunday of the month
because Celery crontab day_of_week + day_of_month uses OR semantics.
"""

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

GROUP_NAME = "wf1-discovery-pipeline"

# 2nd Sunday of the month: day 8-14
_NTH_SUNDAY_MIN = 8
_NTH_SUNDAY_MAX = 14


def _is_2nd_sunday(now: datetime) -> bool:
    """Check if the given date is the 2nd Sunday of its month."""
    return now.weekday() == 6 and _NTH_SUNDAY_MIN <= now.day <= _NTH_SUNDAY_MAX


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline",
)
def optimize_wf1_pipeline(self):
    """Run joint optimization for the WF1 discovery pipeline group.

    Runs monthly via Beat schedule (2nd Sunday 02:00 ET).
    Self-skips if invoked on any other Sunday.
    """
    from app.registries.optimization_groups import get_group

    now = datetime.now(timezone.utc)
    if not _is_2nd_sunday(now):
        logger.info(
            "WF1 optimization skipped: not 2nd Sunday (day=%d, weekday=%d)",
            now.day,
            now.weekday(),
        )
        return {
            "group_name": GROUP_NAME,
            "prompt_count": 0,
            "status": "SKIPPED",
            "reason": "not 2nd Sunday",
        }

    logger.info("Starting WF1 pipeline optimization: group=%s", GROUP_NAME)

    try:
        group = get_group(GROUP_NAME)
    except KeyError as exc:
        logger.error("WF1 optimization failed: %s", exc)
        return {
            "group_name": GROUP_NAME,
            "prompt_count": 0,
            "status": "FAILED",
            "error": str(exc),
        }

    logger.info(
        "WF1 optimization group loaded: %d prompts, agents=%s",
        len(group.prompt_names),
        group.agent_codes,
    )

    from app.scorers import COMMON_SCORERS, WF1_SCORERS
    from app.tasks.optimization_runner import run_group_optimization

    return run_group_optimization(
        group_name=GROUP_NAME,
        scorers=COMMON_SCORERS + WF1_SCORERS,
        celery_task_self=self,
    )
