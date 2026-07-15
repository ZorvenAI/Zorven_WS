"""Celery tasks: optimize WF3 pipeline prompts (§14.1).

Two tasks:
- optimize_wf3_creative_pipeline: CAA + CGA + ADPUB (wf3-creative-pipeline)
- optimize_wf3_optimization_loop: COA + ILA (wf3-optimization-loop)

Both are scheduled weekly via Beat but self-skip based on the effective
WF3 optimization schedule. The effective schedule is the most aggressive
schedule across all tenants (US-047): biweekly > monthly > quarterly > on-demand.

Schedule options: on-demand, biweekly, monthly, quarterly.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

WF3_CREATIVE_GROUP = "wf3-creative-pipeline"
WF3_OPTLOOP_GROUP = "wf3-optimization-loop"

# Quarter start months
_QUARTER_START_MONTHS = {1, 4, 7, 10}

# Schedule priority: lower number = more aggressive (US-047)
SCHEDULE_PRIORITY = {"biweekly": 0, "monthly": 1, "quarterly": 2, "on-demand": 3}


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
        # Run on even ISO weeks (week 2, 4, 6, ...) — Sunday only
        return now.weekday() == 6 and now.isocalendar()[1] % 2 == 0

    if schedule == "monthly":
        # Run only on the 1st Sunday of the month (day 1-7, weekday=Sunday)
        return now.weekday() == 6 and now.day <= 7

    if schedule == "quarterly":
        # Run only on the 1st Sunday of a quarter-start month
        return (
            now.weekday() == 6 and now.month in _QUARTER_START_MONTHS and now.day <= 7
        )

    # Unknown schedule string — treat as on-demand (skip)
    logger.warning("Unknown WF3 schedule '%s', treating as on-demand", schedule)
    return False


def _get_effective_schedule() -> str:
    """Read the most aggressive WF3 schedule across all tenants (US-047).

    Scans all tenant schedule configs from Redis and returns the most
    aggressive one (biweekly > monthly > quarterly > on-demand).
    Falls back to DEFAULT_SCHEDULE if no tenants have custom schedules.
    """
    from app.cache.prompt_cache import PromptCacheManager
    from app.cache.tenant_config import DEFAULT_SCHEDULE, TenantConfigManager
    from app.core.config import settings

    async def _scan() -> dict[str, str]:
        cache = PromptCacheManager(settings.PROMPT_CACHE_REDIS_URL)
        await cache.connect()
        try:
            mgr = TenantConfigManager(prompt_cache=cache)
            return await mgr.get_all_tenant_schedules()
        finally:
            await cache.close()

    schedules = asyncio.run(_scan())

    if not schedules:
        return DEFAULT_SCHEDULE

    return min(
        schedules.values(),
        key=lambda s: SCHEDULE_PRIORITY.get(s, 3),
    )


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline",
)
def optimize_wf3_creative_pipeline(self, force: bool = False):
    """Optimize the WF3 creative pipeline group (CAA + CGA + ADPUB).

    Fires weekly via Beat; self-skips based on effective per-tenant schedule (US-047).
    Pass force=True to bypass the schedule guard (used by campaign trigger).
    """
    from app.registries.optimization_groups import get_group

    if not force:
        schedule = _get_effective_schedule()
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
    else:
        schedule = "on-demand"

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

    from app.scorers import CAA_SCORERS, CGA_SCORERS, COMMON_SCORERS
    from app.tasks.optimization_runner import run_group_optimization

    return run_group_optimization(
        group_name=WF3_CREATIVE_GROUP,
        scorers=COMMON_SCORERS + CAA_SCORERS + CGA_SCORERS,
        celery_task_self=self,
    )


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop",
)
def optimize_wf3_optimization_loop(self, force: bool = False):
    """Optimize the WF3 optimization loop group (COA + ILA).

    Fires weekly via Beat; self-skips based on effective per-tenant schedule (US-047).
    Inherits the same schedule as wf3_creative_pipeline per §14.1.
    Pass force=True to bypass the schedule guard (used by campaign trigger).
    """
    from app.registries.optimization_groups import get_group

    if not force:
        schedule = _get_effective_schedule()
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
    else:
        schedule = "on-demand"

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

    from app.scorers import COA_SCORERS, COMMON_SCORERS, ILA_SCORERS
    from app.tasks.optimization_runner import run_group_optimization

    return run_group_optimization(
        group_name=WF3_OPTLOOP_GROUP,
        scorers=COMMON_SCORERS + COA_SCORERS + ILA_SCORERS,
        celery_task_self=self,
    )
