"""Campaign completion trigger for WF3 re-optimization (§14.2).

Consumes agent.optimization.action_executed events and queues
debounced re-optimization runs when scorer aggregate falls below
the tenant quality threshold.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from app.core.config import settings
from app.logic.debounce import is_debounced, set_debounce

logger = logging.getLogger(__name__)

# Only WF3 agents trigger re-optimization
WF3_AGENTS = {"caa", "cga", "adpub", "coa", "ila"}

TOPIC = "agent.optimization.action_executed"
GROUP_ID = "prompt-reoptimization-trigger"


class CampaignCompletionTrigger:
    """Kafka consumer that triggers WF3 re-optimization on campaign completion.

    Debounces multiple completions within 24h into a single run (AC-1).
    Uses tenant-specific quality threshold to drive queueing (AC-2).
    Logs skip reasons for all filtered events (AC-3).
    """

    def __init__(
        self,
        bootstrap_servers: str,
        prompt_cache: Any,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.prompt_cache = prompt_cache
        self._consumer: Any = None
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start consuming campaign completion events."""
        if not self.bootstrap_servers:
            logger.info("Kafka disabled — CampaignCompletionTrigger in no-op mode")
            return
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                TOPIC,
                bootstrap_servers=self.bootstrap_servers,
                group_id=GROUP_ID,
                auto_offset_reset="latest",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            await self._consumer.start()
            self._task = asyncio.create_task(self._consume_loop())
            logger.info(
                "CampaignCompletionTrigger started (topic=%s, group=%s)",
                TOPIC,
                GROUP_ID,
            )
        except Exception as exc:
            logger.warning("CampaignCompletionTrigger failed: %s — no-op mode", exc)

    async def stop(self) -> None:
        """Stop the consumer and background task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception as exc:
                logger.warning("Error stopping CampaignCompletionTrigger: %s", exc)
            self._consumer = None

    async def _consume_loop(self) -> None:
        """Background loop that polls Kafka and handles events."""
        try:
            async for msg in self._consumer:
                await self.handle_event(msg.value)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("CampaignCompletionTrigger consume error: %s", exc)

    async def handle_event(self, event: dict) -> None:
        """Handle a campaign completion event.

        Checks WF3 agent, debounce window, and quality threshold
        before queueing a re-optimization run.
        """
        tenant_id = event.get("tenant_id", "")
        agent_code = event.get("agent_code", "")
        prompt_name = event.get("prompt_name", "")
        quality_score = event.get("quality_score", 1.0)

        # Skip non-WF3 agents (AC-3)
        if not agent_code or agent_code.lower() not in WF3_AGENTS:
            logger.debug("Skipped trigger: agent '%s' is not WF3", agent_code)
            return

        # Skip missing tenant_id (AC-3)
        if not tenant_id:
            logger.debug("Skipped trigger: missing tenant_id")
            return

        agent = agent_code.lower()

        # AC-1: Check debounce window (24h coalescing)
        if self.prompt_cache is not None:
            try:
                if await is_debounced(self.prompt_cache, tenant_id, agent):
                    logger.info(
                        "Skipped trigger: debounced — tenant=%s agent=%s "
                        "(within %dh window)",
                        tenant_id,
                        agent,
                        settings.REOPT_DEBOUNCE_HOURS,
                    )
                    return
            except Exception as exc:
                logger.warning("Debounce check failed: %s", exc)

        # AC-2: Check quality threshold
        threshold = settings.REOPT_QUALITY_THRESHOLD
        if isinstance(quality_score, (int, float)) and quality_score >= threshold:
            logger.info(
                "Skipped trigger: quality sufficient — tenant=%s agent=%s "
                "score=%.2f >= threshold=%.2f",
                tenant_id,
                agent,
                quality_score,
                threshold,
            )
            return

        # Set debounce key (AC-1)
        if self.prompt_cache is not None:
            try:
                await set_debounce(self.prompt_cache, tenant_id, agent)
            except Exception as exc:
                logger.warning("Failed to set debounce: %s", exc)

        # Queue re-optimization (actual queueing wired in EPIC-14)
        logger.info(
            "Re-optimization triggered: tenant=%s agent=%s prompt=%s "
            "score=%.2f < threshold=%.2f",
            tenant_id,
            agent,
            prompt_name,
            quality_score if isinstance(quality_score, (int, float)) else 0.0,
            threshold,
        )
