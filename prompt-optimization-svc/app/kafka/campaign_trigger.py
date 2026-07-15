"""Campaign completion trigger for WF3 re-optimization (§14.2).

Consumes agent.optimization.action_executed events and logs
re-optimization intent when scorer aggregate falls below the
quality threshold. Actual run queueing is wired in EPIC-14.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from app.core.config import settings
from app.logic.debounce import try_acquire_debounce

logger = logging.getLogger(__name__)

# Only WF3 agents trigger re-optimization
WF3_AGENTS = {"caa", "cga", "adpub", "coa", "ila"}

TOPIC = "agent.optimization.action_executed"
GROUP_ID = "prompt-reoptimization-trigger"

# Per-tenant quality threshold Redis key template (AC-2)
TENANT_THRESHOLD_KEY = "tenant:{tenant_id}:config.reopt_quality_threshold"


class CampaignCompletionTrigger:
    """Kafka consumer that detects WF3 re-optimization opportunities.

    Debounces multiple completions within 24h into a single trigger (AC-1).
    Uses per-tenant quality threshold with global default fallback (AC-2).
    Logs skip reasons at INFO level for all filtered events (AC-3).

    Note: actual run queueing is wired in EPIC-14 — this story logs
    the trigger intent and sets the debounce key.
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
        """Background loop — each message handled independently."""
        try:
            async for msg in self._consumer:
                try:
                    await self.handle_event(msg.value or {})
                except Exception as exc:
                    logger.error("Error handling campaign event: %s", exc)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("CampaignCompletionTrigger consume loop error: %s", exc)

    async def _get_tenant_threshold(self, tenant_id: str) -> float:
        """Get per-tenant quality threshold from Redis, with global fallback.

        AC-2: tenant-specific threshold drives the queueing decision.
        """
        if self.prompt_cache is not None:
            try:
                r = await self.prompt_cache.connect()
                key = TENANT_THRESHOLD_KEY.format(tenant_id=tenant_id)
                val = await r.get(key)
                if val is not None:
                    return float(val)
            except Exception:
                pass
        return settings.REOPT_QUALITY_THRESHOLD

    async def handle_event(self, event: dict) -> None:
        """Handle a campaign completion event.

        Checks WF3 agent, debounce window, and quality threshold
        before logging re-optimization intent.
        """
        tenant_id = event.get("tenant_id", "")
        agent_code = event.get("agent_code", "")
        prompt_name = event.get("prompt_name", "")

        # Parse quality_score safely
        raw_score = event.get("quality_score")
        try:
            quality_score = float(raw_score) if raw_score is not None else 1.0
        except (TypeError, ValueError):
            logger.info("Skipped trigger: invalid quality_score '%s'", raw_score)
            return

        # Skip non-WF3 agents (AC-3)
        if not agent_code or agent_code.lower() not in WF3_AGENTS:
            logger.info("Skipped trigger: agent '%s' is not WF3", agent_code)
            return

        # Skip missing tenant_id (AC-3)
        if not tenant_id:
            logger.info("Skipped trigger: missing tenant_id")
            return

        agent = agent_code.lower()

        # AC-2: Check per-tenant quality threshold
        threshold = await self._get_tenant_threshold(tenant_id)
        if quality_score >= threshold:
            logger.info(
                "Skipped trigger: quality sufficient — tenant=%s agent=%s "
                "score=%.2f >= threshold=%.2f",
                tenant_id,
                agent,
                quality_score,
                threshold,
            )
            return

        # AC-1: Atomic debounce check-and-set (24h coalescing)
        if self.prompt_cache is not None:
            try:
                acquired = await try_acquire_debounce(
                    self.prompt_cache, tenant_id, agent
                )
                if not acquired:
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

        # Log re-optimization intent and enqueue the appropriate task
        logger.info(
            "Re-optimization triggered: tenant=%s agent=%s prompt=%s "
            "score=%.2f < threshold=%.2f",
            tenant_id,
            agent,
            prompt_name,
            quality_score,
            threshold,
        )

        # Enqueue the appropriate WF3 optimization task (force=True bypasses schedule guard)
        try:
            if agent in {"caa", "cga", "adpub"}:
                from app.tasks.optimize_wf3_pipeline import (
                    optimize_wf3_creative_pipeline,
                )

                optimize_wf3_creative_pipeline.apply_async(kwargs={"force": True})
                logger.info(
                    "Enqueued WF3 creative pipeline re-optimization for tenant=%s",
                    tenant_id,
                )
            elif agent in {"coa", "ila"}:
                from app.tasks.optimize_wf3_pipeline import (
                    optimize_wf3_optimization_loop,
                )

                optimize_wf3_optimization_loop.apply_async(kwargs={"force": True})
                logger.info(
                    "Enqueued WF3 optimization loop re-optimization for tenant=%s",
                    tenant_id,
                )
        except Exception as enqueue_exc:
            logger.error(
                "Failed to enqueue re-optimization task: tenant=%s agent=%s error=%s",
                tenant_id,
                agent,
                enqueue_exc,
            )
