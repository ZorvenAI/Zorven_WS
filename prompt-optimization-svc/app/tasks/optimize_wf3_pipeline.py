"""Celery tasks: optimize WF3 pipeline prompts (§14.1).

Two tasks:
- optimize_wf3_creative_pipeline: CAA + CGA + ADPUB (wf3-creative-pipeline)
- optimize_wf3_optimization_loop: COA + ILA (wf3-optimization-loop)

Both are scheduled weekly via Beat but self-skip based on the tenant
wf3_optimization_schedule config (AC-2). Default is 'on-demand' which
means the Beat-fired task is a no-op.

Schedule options: on-demand, biweekly, monthly, quarterly.
"""

import logging
from datetime import datetime, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

WF3_CREATIVE_GROUP = "wf3-creative-pipeline"
WF3_OPTLOOP_GROUP = "wf3-optimization-loop"

# Quarter start months
_QUARTER_START_MONTHS = {1, 4, 7, 10}


def should_run_wf3_schedule(schedule: str, now: datetime) -> bool:
    """Decide whether a WF3 task should execute based on tenant schedule.

    Args:
        schedule: One of 'on-demand', 'biweekly', 'monthly', 'quarterly'.
        now: Current UTC datetime.

    Returns:
        True if the task should run this invocation, False to skip.
    """
    if schedule == "on-demand":
        return False

    if schedule == "biweekly":
        # Run on even ISO weeks (week 2, 4, 6, ...)
        return now.isocalendar()[1] % 2 == 0

    if schedule == "monthly":
        # Run only on the 1st Sunday of the month (day 1-7)
        return now.day <= 7

    if schedule == "quarterly":
        # Run only on the 1st Sunday of a quarter-start month
        return now.month in _QUARTER_START_MONTHS and now.day <= 7

    # Unknown schedule string — treat as on-demand (skip)
    logger.warning("Unknown WF3 schedule '%s', treating as on-demand", schedule)
    return False


def _get_default_schedule() -> str:
    """Get the default WF3 schedule from tenant config defaults."""
    from app.cache.tenant_config import DEFAULT_SCHEDULE

    return DEFAULT_SCHEDULE


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline",
)
def optimize_wf3_creative_pipeline(self):
    """Optimize the WF3 creative pipeline group (CAA + CGA + ADPUB).

    Fires weekly via Beat; self-skips based on tenant schedule config (AC-2).
    """
    from app.registries.optimization_groups import get_group

    schedule = _get_default_schedule()
    now = datetime.now(timezone.utc)

    if not should_run_wf3_schedule(schedule, now):
        logger.info(
            "WF3 creative pipeline skipped: schedule=%s, date=%s",
            schedule,
            now.isoformat(),
        )
        return {
            "group_name": WF3_CREATIVE_GROUP,
            "prompt_count": 0,
            "status": "SKIPPED",
            "schedule": schedule,
        }

    logger.info("Starting WF3 creative pipeline optimization: schedule=%s", schedule)

    try:
        group = get_group(WF3_CREATIVE_GROUP)
    except KeyError as exc:
        logger.error("WF3 creative optimization failed: %s", exc)
        return {
            "group_name": WF3_CREATIVE_GROUP,
            "prompt_count": 0,
            "status": "FAILED",
            "schedule": schedule,
            "error": str(exc),
        }

    return {
        "group_name": WF3_CREATIVE_GROUP,
        "prompt_count": len(group.prompt_names),
        "agent_codes": list(group.agent_codes),
        "status": "TRIGGERED",
        "schedule": schedule,
    }


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop",
)
def optimize_wf3_optimization_loop(self):
    """Optimize the WF3 optimization loop group (COA + ILA).

    Fires weekly via Beat; self-skips based on tenant schedule config (AC-2).
    Inherits the same schedule as wf3_creative_pipeline per §14.1.
    """
    from app.registries.optimization_groups import get_group

    schedule = _get_default_schedule()
    now = datetime.now(timezone.utc)

    if not should_run_wf3_schedule(schedule, now):
        logger.info(
            "WF3 optimization loop skipped: schedule=%s, date=%s",
            schedule,
            now.isoformat(),
        )
        return {
            "group_name": WF3_OPTLOOP_GROUP,
            "prompt_count": 0,
            "status": "SKIPPED",
            "schedule": schedule,
        }

    logger.info("Starting WF3 optimization loop optimization: schedule=%s", schedule)

    try:
        group = get_group(WF3_OPTLOOP_GROUP)
    except KeyError as exc:
        logger.error("WF3 optimization loop failed: %s", exc)
        return {
            "group_name": WF3_OPTLOOP_GROUP,
            "prompt_count": 0,
            "status": "FAILED",
            "schedule": schedule,
            "error": str(exc),
        }

    return {
        "group_name": WF3_OPTLOOP_GROUP,
        "prompt_count": len(group.prompt_names),
        "agent_codes": list(group.agent_codes),
        "status": "TRIGGERED",
        "schedule": schedule,
    }
