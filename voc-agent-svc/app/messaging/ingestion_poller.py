"""Polling fallback for continuous Odoo ingestion.

Activates when Kafka circuit breaker is OPEN or bootstrap fails.
Reads Odoo via OdooRPCClient every INGESTION_POLL_INTERVAL seconds
using since_date = last_ingestion from the registry.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.messaging.ingestion_consumer import _quick_sentiment
from app.registry.models import (
    ChatterFeedback,
    SurveyFeedback,
    TicketFeedback,
    hash_customer_id,
)

logger = logging.getLogger(__name__)


class IngestionPoller:
    """Polls Odoo RPC for new feedback when Kafka is unavailable."""

    def __init__(
        self,
        odoo_client: Any,
        feedback_registry: Any,
        redis_manager: Any,
        poll_interval: int | None = None,
    ) -> None:
        self._odoo = odoo_client
        self._registry = feedback_registry
        self._redis = redis_manager
        self._interval = poll_interval or settings.INGESTION_POLL_INTERVAL
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, tenant_id: str) -> None:
        """Start the polling loop for a tenant."""
        self._running = True
        self._task = asyncio.create_task(
            self._poll_loop(tenant_id)
        )
        logger.info(
            "IngestionPoller started: tenant=%s, interval=%ds",
            tenant_id,
            self._interval,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self, tenant_id: str) -> None:
        while self._running:
            try:
                await self._poll_once(tenant_id)
            except Exception as exc:
                logger.error("Polling error: %s", exc)
            await asyncio.sleep(self._interval)

    async def _poll_once(self, tenant_id: str) -> None:
        """One poll cycle: read new tickets, surveys, chatter since last run."""
        last_ingestion = await self._redis.get_tenant_config(
            tenant_id, "last_ingestion"
        )
        since = last_ingestion or "1970-01-01T00:00:00"
        now = datetime.now(timezone.utc).isoformat()

        count = 0

        # Poll helpdesk tickets
        try:
            tickets = await self._odoo.search_read(
                "project.task",
                [["write_date", ">", since]],
                ["name", "description", "partner_id", "priority", "stage_id"],
                limit=100,
            )
            for t in tickets:
                text = t.get("description", "") or t.get("name", "")
                label, score = _quick_sentiment(text)
                pid = t.get("partner_id")
                cid = pid[0] if isinstance(pid, (list, tuple)) else pid or 0
                fb = TicketFeedback(
                    feedback_id=f"poll-{uuid.uuid4().hex[:12]}",
                    customer_id_hash=hash_customer_id(cid) if cid else "",
                    text=text[:2000],
                    timestamp=now,
                    sentiment_label=label,
                    sentiment_score=score,
                    ticket_id=t.get("id", 0),
                    priority=str(t.get("priority", "")),
                    stage=str(
                        t["stage_id"][1]
                        if isinstance(t.get("stage_id"), (list, tuple))
                        else t.get("stage_id", "")
                    ),
                )
                await self._registry.add_feedback(tenant_id, fb)
                count += 1
        except Exception as exc:
            logger.warning("Ticket polling failed: %s", exc)

        # Poll chatter messages
        try:
            messages = await self._odoo.search_read(
                "mail.message",
                [
                    ["date", ">", since],
                    ["message_type", "=", "comment"],
                    ["subtype_id.internal", "=", False],
                ],
                ["body", "model", "res_id", "author_id", "date"],
                limit=200,
            )
            for m in messages:
                text = m.get("body", "")
                label, score = _quick_sentiment(text)
                aid = m.get("author_id")
                cid = aid[0] if isinstance(aid, (list, tuple)) else aid or 0
                fb = ChatterFeedback(
                    feedback_id=f"poll-{uuid.uuid4().hex[:12]}",
                    customer_id_hash=hash_customer_id(cid) if cid else "",
                    text=text[:2000],
                    timestamp=now,
                    sentiment_label=label,
                    sentiment_score=score,
                    model=m.get("model", ""),
                    record_id=m.get("res_id", 0),
                    message_type="comment",
                )
                await self._registry.add_feedback(tenant_id, fb)
                count += 1
        except Exception as exc:
            logger.warning("Chatter polling failed: %s", exc)

        if count > 0:
            logger.info("Polled %d new feedback items for tenant=%s", count, tenant_id)

        # Update last ingestion timestamp
        if self._redis._redis:
            try:
                await self._redis._redis.set(
                    f"voca:{tenant_id}:registry:last_ingestion", now
                )
            except Exception:
                pass
