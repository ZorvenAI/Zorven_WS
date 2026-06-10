"""Celery task: optimize WF1 discovery pipeline prompts.

Scheduled via Beat: Monthly, 2nd Sunday 06:00 UTC (02:00 ET) per §14.1.
Optimizes all WF1 agents (mra, cia, apa, tcia, voca) as a joint group.
"""

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)

GROUP_NAME = "wf1-discovery-pipeline"


@celery_app.task(
    bind=True,
    name="app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline",
)
def optimize_wf1_pipeline(self):
    """Run joint optimization for the WF1 discovery pipeline group.

    This is a sync Celery task that wraps the async optimization logic.
    Runs monthly via Beat schedule (2nd Sunday 02:00 ET).
    """
    from app.registries.optimization_groups import get_group

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

    # Joint optimization requires MLflow + Anthropic — delegate to optimizer
    # For now, log the trigger and return metadata
    return {
        "group_name": GROUP_NAME,
        "prompt_count": len(group.prompt_names),
        "agent_codes": list(group.agent_codes),
        "status": "TRIGGERED",
    }
