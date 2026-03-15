"""Scheduled scan consumer for the Voice of Customer Agent.

Consumes from: agent.commands.voice-of-customer-agent
Supports: full (monthly comprehensive) and incremental (weekly sentiment)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ScheduledScanConsumer:
    """Consumes scheduled scan commands from Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        consumer_group: str,
        executor: Any,
        redis_manager: Any,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._group = consumer_group
        self._executor = executor
        self._redis = redis_manager
        self._consumer = None
        self._running = False
        self._topic = "agent.commands.voice-of-customer-agent"

    async def start(self) -> None:
        if not self._bootstrap:
            logger.info("ScheduledScanConsumer in stub mode")
            return
        try:
            from aiokafka import AIOKafkaConsumer

            self._consumer = AIOKafkaConsumer(
                self._topic,
                bootstrap_servers=self._bootstrap,
                group_id=self._group,
                value_deserializer=lambda v: json.loads(v.decode()),
                auto_offset_reset="latest",
            )
            await self._consumer.start()
            self._running = True
            asyncio.create_task(self._consume_loop())
            logger.info(
                "ScheduledScanConsumer started: %s (group=%s)",
                self._topic,
                self._group,
            )
        except Exception as exc:
            logger.warning("ScheduledScanConsumer start failed: %s", exc)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()

    async def _consume_loop(self) -> None:
        while self._running and self._consumer:
            try:
                async for msg in self._consumer:
                    if not self._running:
                        break
                    await self._handle_message(msg.value)
            except Exception as exc:
                logger.error("Consumer loop error: %s", exc)
                if self._running:
                    await asyncio.sleep(5)

    async def _handle_message(self, value: dict[str, Any]) -> None:
        scan_type = value.get("scan_type", "full")
        payload = value.get("payload", {})
        tenant_id = payload.get("tenant_id", "")

        if not tenant_id:
            logger.warning("Scan command missing tenant_id, skipping")
            return

        # Idempotency check
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        idem_key = f"voc:{scan_type}:{tenant_id}:{today}"
        is_new = await self._redis.check_idempotency(idem_key)
        if not is_new:
            logger.info("Duplicate scan command, skipping: %s", idem_key)
            return

        logger.info(
            "Processing scheduled scan: type=%s, tenant=%s",
            scan_type,
            tenant_id,
        )

        prompt = (
            f"Run {scan_type} voice of customer analysis"
            f" for {payload.get('company_name', 'the company')}"
        )
        if payload.get("industry"):
            prompt += f" in the {payload['industry']} industry"

        try:
            await self._executor.execute(
                prompt=prompt,
                input_context={
                    "company_name": payload.get("company_name", ""),
                    "sector": payload.get("industry", ""),
                    "scan_type": scan_type,
                },
                tenant_context={
                    "tenant_id": tenant_id,
                    "user_role": "ADMIN",
                },
                config={
                    "scan_type": scan_type,
                    "focus_areas": payload.get("focus_areas", []),
                },
                previous_outputs={},
                tenant_id=tenant_id,
            )
            logger.info("Scheduled scan completed: %s", idem_key)
        except Exception as exc:
            logger.error("Scheduled scan failed: %s — %s", idem_key, exc)
