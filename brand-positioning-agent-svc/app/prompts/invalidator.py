"""Prompt cache invalidation consumer (AC-3).

Subscribes to prompt-lifecycle-events Kafka topic and invalidates
local prompt cache when a prompt is promoted to PRODUCTION.
"""

import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PromptCacheInvalidator:
    """Kafka consumer that invalidates cached prompts on promotion events."""

    TOPIC = "prompt-lifecycle-events"
    GROUP_ID = "prompt-cache-invalidator-bpa"

    def __init__(
        self,
        bootstrap_servers: str,
        prompt_loader: Any,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.prompt_loader = prompt_loader
        self._consumer: Any = None
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start consuming prompt lifecycle events."""
        if not self.bootstrap_servers:
            logger.info("Kafka disabled — PromptCacheInvalidator in no-op mode")
            return
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                self.TOPIC,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.GROUP_ID,
                auto_offset_reset="latest",
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            )
            await asyncio.wait_for(self._consumer.start(), timeout=10.0)
            self._task = asyncio.create_task(self._consume_loop())
            logger.info(
                "PromptCacheInvalidator started (topic=%s, group=%s)",
                self.TOPIC,
                self.GROUP_ID,
            )
        except Exception as exc:
            logger.warning("PromptCacheInvalidator failed: %s — no-op mode", exc)
            self._consumer = None

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
                logger.warning("Error stopping PromptCacheInvalidator: %s", exc)
            self._consumer = None

    async def _consume_loop(self) -> None:
        """Background loop that polls Kafka and handles events."""
        try:
            async for msg in self._consumer:
                await self.handle_event(msg.value)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("PromptCacheInvalidator consume error: %s", exc)

    async def handle_event(self, event: dict) -> None:
        """Handle a prompt lifecycle event."""
        event_type = event.get("event_type", "")
        prompt_name = event.get("prompt_name", "")

        if event_type == "prompt.promoted" and prompt_name:
            logger.info("Invalidating cache for promoted prompt: %s", prompt_name)
            if self.prompt_loader and hasattr(self.prompt_loader, "_redis"):
                try:
                    r = self.prompt_loader._redis
                    if r:
                        deleted = 0
                        batch = []
                        async for key in r.scan_iter(match=f"prompt:{prompt_name}:*"):
                            batch.append(key)
                            if len(batch) >= 100:
                                await r.delete(*batch)
                                deleted += len(batch)
                                batch = []
                        if batch:
                            await r.delete(*batch)
                            deleted += len(batch)
                        if deleted:
                            logger.info(
                                "Invalidated %d cache keys for %s",
                                deleted,
                                prompt_name,
                            )
                except Exception as exc:
                    logger.warning("Cache invalidation failed: %s", exc)
