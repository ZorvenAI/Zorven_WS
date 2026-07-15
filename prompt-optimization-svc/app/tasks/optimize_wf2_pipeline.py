"""Celery task: optimize WF2 brand strategy pipeline prompts.

Scheduled via Beat: Monthly, 3rd Sunday 06:00 UTC (02:00 ET) per §14.1.
Optimizes all WF2 agents (bpa, baa, bpv, nta, bsa) as a joint group.

Beat fires every Sunday; task self-guards for the 3rd Sunday of the month
because Celery crontab day_of_week + day_of_month uses OR semantics.
"""

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

GROUP_NAME = "wf2-brand-strategy-pipeline"

# 3rd Sunday of the month: day 15-21
_NTH_SUNDAY_MIN = 15
_NTH_SUNDAY_MAX = 21


def _is_3rd_sunday(now: datetime) -> bool:
    """Check if the given date is the 3rd Sunday of its month."""
    return now.weekday() == 6 and _NTH_SUNDAY_MIN <= now.day <= _NTH_SUNDAY_MAX


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline",
)
def optimize_wf2_pipeline(self):
    """Run joint optimization for the WF2 brand strategy pipeline group.

    Runs monthly via Beat schedule (3rd Sunday 02:00 ET).
    Self-skips if invoked on any other Sunday.
    """
    from app.registries.optimization_groups import get_group

    now = datetime.now(timezone.utc)
    if not _is_3rd_sunday(now):
        logger.info(
            "WF2 optimization skipped: not 3rd Sunday (day=%d, weekday=%d)",
            now.day,
            now.weekday(),
        )
        return {
            "group_name": GROUP_NAME,
            "prompt_count": 0,
            "status": "SKIPPED",
            "reason": "not 3rd Sunday",
        }

    logger.info("Starting WF2 pipeline optimization: group=%s", GROUP_NAME)

    try:
        group = get_group(GROUP_NAME)
    except KeyError as exc:
        logger.error("WF2 optimization failed: %s", exc)
        return {
            "group_name": GROUP_NAME,
            "prompt_count": 0,
            "status": "FAILED",
            "error": str(exc),
        }

    logger.info(
        "WF2 optimization group loaded: %d prompts, agents=%s",
        len(group.prompt_names),
        group.agent_codes,
    )

    from app.scorers import COMMON_SCORERS, WF2_SCORERS
    from app.tasks.optimization_runner import run_group_optimization

    return run_group_optimization(
        group_name=GROUP_NAME,
        scorers=COMMON_SCORERS + WF2_SCORERS,
        celery_task_self=self,
    )
