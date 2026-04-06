"""Kafka consumer for Campaign Optimization Agent.

Consumes from agent.optimization.spend_milestone topic (self-trigger).
On receive, triggers an immediate optimization tick for the specified campaign.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

TOPIC = "agent.optimization.spend_milestone"


class SpendMilestoneConsumer:
    """Consumes spend milestone events to trigger immediate optimization ticks."""

    def __init__(self, bootstrap_servers: str):
        self._bootstrap_servers = bootstrap_servers
        self._consumer = None
        self._running = False

    async def start(self):
        """Start consuming spend milestone events."""
        if not self._bootstrap_servers:
            logger.info(
                "Kafka consumer for %s in stub mode "
                "(no bootstrap servers)",
                TOPIC,
            )
            return
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                TOPIC,
                bootstrap_servers=self._bootstrap_servers,
                group_id="coa-spend-milestone-group",
                value_deserializer=lambda v: json.loads(v.decode()),
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._running = True
            logger.info("Kafka consumer started for topic: %s", TOPIC)
        except Exception as exc:
            logger.warning(
                "Kafka consumer start failed for %s: %s", TOPIC, exc
            )
            self._consumer = None

    async def stop(self):
        """Stop consumer."""
        self._running = False
        if self._consumer:
            try:
                await self._consumer.stop()
            except Exception:
                pass

    async def consume_loop(self):
        """Main consume loop. Triggers optimization tick on each message.

        Should be run as an asyncio task.
        """
        if not self._consumer:
            return
        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                await self._handle_message(msg.value)
        except Exception as exc:
            logger.error("Spend milestone consumer loop error: %s", exc)

    async def _handle_message(self, data: dict[str, Any]):
        """Handle a spend milestone event by triggering an optimization tick."""
        tenant_id = data.get("tenant_id", "")
        campaign_id = data.get("campaign_id", "")
        milestone = data.get("milestone", "")

        logger.info(
            "Spend milestone received: tenant=%s campaign=%s milestone=%s",
            tenant_id,
            campaign_id,
            milestone,
        )

        try:
            from app.tasks import run_optimization_tick

            run_optimization_tick.delay(
                campaign_age_min_days=None,
                campaign_age_max_days=None,
            )
            logger.info(
                "Triggered immediate tick for campaign %s", campaign_id
            )
        except Exception as exc:
            logger.error(
                "Failed to trigger tick for campaign %s: %s",
                campaign_id,
                exc,
            )
