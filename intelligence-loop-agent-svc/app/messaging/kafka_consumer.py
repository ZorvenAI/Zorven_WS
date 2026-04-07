"""Kafka consumer for ILA — fans events into the extractor.

Subscribes to:
- agent.optimization.action_executed (per-action COA learnings)
- campaign.completed                  (end-of-campaign roll-up)

Both events MUST carry: tenant_id, campaign_id, job_id (optional).
Events without those keys are dropped with a warning. Fail-open: if
no Kafka brokers are configured the consumer never starts and the
extractor still works via /v1/execute.
"""

import asyncio
import json
import logging
from typing import Any

from app.core.config import settings
from app.services.extractor import IntelligenceExtractor

logger = logging.getLogger(__name__)

try:
    from aiokafka import AIOKafkaConsumer
except ImportError:  # pragma: no cover
    AIOKafkaConsumer = None  # type: ignore

TOPICS = ("agent.optimization.action_executed", "campaign.completed")


class IlaKafkaConsumer:
    def __init__(self, extractor: IntelligenceExtractor) -> None:
        self._extractor = extractor
        self._consumer: Any = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not settings.KAFKA_BOOTSTRAP_SERVERS or AIOKafkaConsumer is None:
            logger.info("Kafka consumer disabled (no brokers)")
            return
        try:
            self._consumer = AIOKafkaConsumer(
                *TOPICS,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id="intelligence-loop-agent",
                value_deserializer=lambda v: json.loads(v.decode()),
                enable_auto_commit=True,
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._task = asyncio.create_task(self._run())
            logger.info("Kafka consumer started topics=%s", TOPICS)
        except Exception as exc:
            logger.warning("Kafka consumer start failed (fail-open): %s", exc)
            self._consumer = None

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self._consumer:
            try:
                await self._consumer.stop()
            except Exception:
                pass

    async def _run(self) -> None:
        async for msg in self._consumer:
            try:
                await self._handle(msg.topic, msg.value or {})
            except Exception as exc:
                logger.exception("ILA event handler failed: %s", exc)

    async def _handle(self, topic: str, payload: dict[str, Any]) -> None:
        tenant_id = payload.get("tenant_id")
        campaign_id = payload.get("campaign_id")
        if not campaign_id:
            logger.warning(
                "Dropping %s event without campaign_id: %s",
                topic,
                list(payload.keys()),
            )
            return
        job_id = payload.get("job_id") or f"kafka:{topic}:{campaign_id}"
        trigger_source = (
            "campaign_completed"
            if topic == "campaign.completed"
            else "coa_event"
        )
        logger.info(
            "ILA Kafka trigger topic=%s campaign=%s tenant=%s",
            topic,
            campaign_id,
            tenant_id,
        )
        await self._extractor.extract(
            job_id=str(job_id),
            tenant_id=str(tenant_id) if tenant_id else None,
            state={"campaign_id": str(campaign_id)},
            context={"trigger_source": trigger_source, **payload},
            config={"default_mode": settings.DEFAULT_MODE},
        )
