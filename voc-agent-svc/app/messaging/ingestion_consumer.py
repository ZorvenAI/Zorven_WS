"""Continuous Odoo event ingestion consumer for the Voice of Customer Agent.

Consumes from: odoo.events.<tid>
Each event triggers lightweight keyword-based sentiment classification
(not LLM) and appends to the feedback registry. LLM analysis is deferred
to scheduled synthesis runs.
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.registry.models import (
    ChatterFeedback,
    FeedbackChannel,
    SurveyFeedback,
    TicketFeedback,
    hash_customer_id,
)

logger = logging.getLogger(__name__)

# Simple keyword-based sentiment classification (not LLM)
_POSITIVE_KEYWORDS = {
    "great",
    "excellent",
    "love",
    "amazing",
    "perfect",
    "fantastic",
    "helpful",
    "solved",
    "resolved",
    "thank",
    "happy",
    "satisfied",
    "recommend",
    "awesome",
}
_NEGATIVE_KEYWORDS = {
    "terrible",
    "awful",
    "horrible",
    "broken",
    "bug",
    "issue",
    "problem",
    "frustrated",
    "angry",
    "disappointed",
    "unresolved",
    "complaint",
    "hate",
    "worst",
    "fail",
    "crash",
}


def _quick_sentiment(text: str) -> tuple[str, float]:
    """Keyword-based sentiment (fast, no LLM)."""
    words = set(re.findall(r"\w+", text.lower()))
    pos = len(words & _POSITIVE_KEYWORDS)
    neg = len(words & _NEGATIVE_KEYWORDS)
    if pos > neg:
        return "positive", min(0.5 + pos * 0.1, 0.9)
    elif neg > pos:
        return "negative", min(0.5 + neg * 0.1, 0.9)
    return "neutral", 0.5


class OdooEventConsumer:
    """Consumes Odoo events for continuous ingestion."""

    def __init__(
        self,
        bootstrap_servers: str,
        consumer_group: str,
        feedback_registry: Any,
        redis_manager: Any,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._group = consumer_group
        self._registry = feedback_registry
        self._redis = redis_manager
        self._consumer = None
        self._running = False

    async def start(self, tenant_ids: list[str] | None = None) -> None:
        """Start consuming from odoo.events.* topics."""
        if not self._bootstrap:
            logger.info("OdooEventConsumer in stub mode")
            return
        try:
            from aiokafka import AIOKafkaConsumer

            # Subscribe to pattern matching tenant topics
            self._consumer = AIOKafkaConsumer(
                bootstrap_servers=self._bootstrap,
                group_id=self._group,
                value_deserializer=lambda v: json.loads(v.decode()),
                auto_offset_reset="latest",
            )
            # Subscribe to wildcard pattern
            self._consumer.subscribe(
                pattern=r"odoo\.events\..*"
            )
            await self._consumer.start()
            self._running = True
            asyncio.create_task(self._consume_loop())
            logger.info("OdooEventConsumer started (group=%s)", self._group)
        except Exception as exc:
            logger.warning("OdooEventConsumer start failed: %s", exc)

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
                    await self._handle_event(msg.value, msg.topic)
            except Exception as exc:
                logger.error("Ingestion consumer loop error: %s", exc)
                if self._running:
                    await asyncio.sleep(5)

    async def _handle_event(
        self, value: dict[str, Any], topic: str
    ) -> None:
        """Process a single Odoo event into a FeedbackItem."""
        event_type = value.get("event_type", "")
        tenant_id = value.get("tenant_id", "")
        data = value.get("data", {})

        if not tenant_id:
            return

        try:
            feedback = self._convert_event(event_type, data, tenant_id)
            if feedback:
                await self._registry.add_feedback(tenant_id, feedback)
                logger.debug(
                    "Ingested event: type=%s, tenant=%s, id=%s",
                    event_type,
                    tenant_id,
                    feedback.feedback_id,
                )
        except Exception as exc:
            logger.warning(
                "Failed to ingest event: type=%s, error=%s",
                event_type,
                exc,
            )

    def _convert_event(
        self, event_type: str, data: dict[str, Any], tenant_id: str
    ) -> TicketFeedback | SurveyFeedback | ChatterFeedback | None:
        """Convert Odoo event to FeedbackItem."""
        now = datetime.now(timezone.utc).isoformat()
        text = data.get("description", "") or data.get("body", "") or ""
        label, score = _quick_sentiment(text)
        customer_id = data.get("partner_id", 0)
        cid_hash = hash_customer_id(customer_id, salt=tenant_id) if customer_id else ""

        if event_type in ("ticket_created", "ticket_updated"):
            return TicketFeedback(
                feedback_id=f"evt-{uuid.uuid4().hex[:12]}",
                customer_id_hash=cid_hash,
                text=text[:2000],
                timestamp=now,
                sentiment_label=label,
                sentiment_score=score,
                ticket_id=data.get("id", 0),
                priority=data.get("priority", ""),
                stage=data.get("stage", ""),
                category=data.get("category", ""),
            )
        elif event_type == "survey_completed":
            return SurveyFeedback(
                feedback_id=f"evt-{uuid.uuid4().hex[:12]}",
                customer_id_hash=cid_hash,
                text=text[:2000],
                timestamp=now,
                sentiment_label=label,
                sentiment_score=score,
                survey_id=data.get("survey_id", 0),
                survey_title=data.get("survey_title", ""),
                question=data.get("question", ""),
                answer=data.get("answer", ""),
                score=data.get("score"),
            )
        elif event_type == "chatter_message":
            return ChatterFeedback(
                feedback_id=f"evt-{uuid.uuid4().hex[:12]}",
                customer_id_hash=cid_hash,
                text=text[:2000],
                timestamp=now,
                sentiment_label=label,
                sentiment_score=score,
                model=data.get("model", ""),
                record_id=data.get("record_id", 0),
                message_type=data.get("message_type", "comment"),
            )
        return None
