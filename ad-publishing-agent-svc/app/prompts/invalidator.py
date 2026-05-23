"""Prompt cache invalidation consumer (AC-3).

Subscribes to prompt.promoted Kafka topic and invalidates local
prompt cache when a prompt is promoted to PRODUCTION.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PromptCacheInvalidator:
    """Kafka consumer that invalidates cached prompts on promotion events."""

    TOPIC = "prompt-lifecycle-events"

    def __init__(
        self,
        bootstrap_servers: str,
        prompt_loader: Any,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.prompt_loader = prompt_loader
        self._consumer: Any = None
        self._running = False

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
                group_id="prompt-cache-invalidator",
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._running = True
            logger.info("PromptCacheInvalidator started on %s", self.TOPIC)
        except Exception as exc:
            logger.warning("PromptCacheInvalidator failed: %s — no-op mode", exc)

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False
        if self._consumer is not None:
            try:
                await self._consumer.stop()
            except Exception as exc:
                logger.warning("Error stopping PromptCacheInvalidator: %s", exc)
            self._consumer = None

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
                        keys = []
                        async for key in r.scan_iter(match=f"prompt:{prompt_name}:*"):
                            keys.append(key)
                        if keys:
                            await r.delete(*keys)
                            logger.info("Invalidated %d cache keys for %s", len(keys), prompt_name)
                except Exception as exc:
                    logger.warning("Cache invalidation failed: %s", exc)
