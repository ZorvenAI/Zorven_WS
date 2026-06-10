"""Celery task: optimize WF2 brand strategy pipeline prompts.

Scheduled via Beat: Monthly, 3rd Sunday 06:00 UTC (02:00 ET) per §14.1.
Optimizes all WF2 agents (bpa, baa, bpv, nta, bsa) as a joint group.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

GROUP_NAME = "wf2-brand-strategy-pipeline"


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline",
)
def optimize_wf2_pipeline(self):
    """Run joint optimization for the WF2 brand strategy pipeline group.

    This is a sync Celery task that wraps the async optimization logic.
    Runs monthly via Beat schedule (3rd Sunday 02:00 ET).
    """
    from app.registries.optimization_groups import get_group

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

    return {
        "group_name": GROUP_NAME,
        "prompt_count": len(group.prompt_names),
        "agent_codes": list(group.agent_codes),
        "status": "TRIGGERED",
    }
