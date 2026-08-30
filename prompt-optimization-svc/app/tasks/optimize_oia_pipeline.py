"""Celery task: optimize OIA onboarding pipeline prompts.

Scheduled via Beat: Monthly, 4th Sunday 06:00 UTC (02:00 ET) per §14.1.
Optimizes all OIA prompts (research, questionnaire, live analysis,
PROCESS extraction) as a joint group.

Beat fires every Sunday; task self-guards for the 4th Sunday of the month
because Celery crontab day_of_week + day_of_month uses OR semantics.
"""

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

GROUP_NAME = "oia-onboarding-pipeline"

# 4th Sunday of the month: day 22-28
_NTH_SUNDAY_MIN = 22
_NTH_SUNDAY_MAX = 28


def _is_4th_sunday(now: datetime) -> bool:
    """Check if the given date is the 4th Sunday of its month."""
    return now.weekday() == 6 and _NTH_SUNDAY_MIN <= now.day <= _NTH_SUNDAY_MAX


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_oia_pipeline.optimize_oia_pipeline",
)
def optimize_oia_pipeline(self, force: bool = False):
    """Run joint optimization for the OIA onboarding pipeline group.

    Runs monthly via Beat schedule (4th Sunday 02:00 ET).
    Self-skips if invoked on any other Sunday.
    Pass force=True to bypass the schedule guard (used by /v1/optimize).
    """
    from app.registries.optimization_groups import get_group

    now = datetime.now(timezone.utc)
    if not force and not _is_4th_sunday(now):
        logger.info(
            "OIA optimization skipped: not 4th Sunday (day=%d, weekday=%d)",
            now.day,
            now.weekday(),
        )
        return {
            "group_name": GROUP_NAME,
            "prompt_count": 0,
            "status": "SKIPPED",
            "reason": "not 4th Sunday",
        }

    logger.info("Starting OIA pipeline optimization: group=%s", GROUP_NAME)

    try:
        group = get_group(GROUP_NAME)
    except KeyError as exc:
        logger.error("OIA optimization failed: %s", exc)
        return {
            "group_name": GROUP_NAME,
            "prompt_count": 0,
            "status": "FAILED",
            "error": str(exc),
        }

    logger.info(
        "OIA optimization group loaded: %d prompts, agents=%s",
        len(group.prompt_names),
        group.agent_codes,
    )

    from app.scorers import COMMON_SCORERS, OIA_SCORERS
    from app.tasks.optimization_runner import run_group_optimization

    return run_group_optimization(
        group_name=GROUP_NAME,
        scorers=COMMON_SCORERS + OIA_SCORERS,
        celery_task_self=self,
    )
