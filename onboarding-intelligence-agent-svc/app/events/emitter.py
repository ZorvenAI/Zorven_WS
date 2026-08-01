"""EventEmitter — the single way this service emits a §12 event.

Three properties are load-bearing:

**Validation raises, it does not warn.** AC-2: "a payload that fails validation
raises rather than silently emitting a malformed event." A malformed event that
reaches the stream is worse than no event, because downstream consumers and the
audit trail both treat the stream as authoritative.

**Emission never fails the caller.** A meeting must not drop because Kafka is
unreachable. Publication is fire-and-forget onto a bounded queue; the envelope
is always recorded as a span event and a structured log line, both of which
survive Kafka being absent entirely — which in production it is, since no
`deployment/gcp` script provisions a broker.

**The trace comes from the active span.** ``trace_id`` and ``span_id`` are read
from the current OpenTelemetry context rather than passed in, so an event
emitted while handling a request carrying a W3C ``traceparent`` is joined to
the caller's trace automatically (AC-3).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from opentelemetry import trace

from app.core.logging import get_logger
from app.events.catalog import AgentEvent, EventType, Outcome, assert_no_pii
from app.messaging.producer import KafkaProducer
from app.messaging.topics import events_topic, message_key

logger = get_logger(__name__)

#: Bounded so a Kafka outage costs memory in a known, small amount rather than
#: growing until the process dies.
MAX_QUEUED_EVENTS = 1000


class EventEmitter:
    """Builds, validates and publishes §12 events."""

    def __init__(self, producer: KafkaProducer) -> None:
        self._producer = producer
        self._queue: asyncio.Queue[tuple[str, str, bytes]] = asyncio.Queue(
            maxsize=MAX_QUEUED_EVENTS
        )
        self._worker: asyncio.Task[None] | None = None
        self.dropped = 0

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def build(
        self,
        event_type: EventType,
        *,
        tenant_id: uuid.UUID | str,
        correlation_id: str,
        session_id: uuid.UUID | str | None = None,
        user_id: uuid.UUID | str | None = None,
        role: str | None = None,
        skill_id: str | None = None,
        payload: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        outcome: Outcome = "SUCCESS",
    ) -> AgentEvent:
        """Construct and validate an envelope. Raises on anything malformed."""
        body = payload or {}
        assert_no_pii(event_type, body)

        span = trace.get_current_span()
        context = span.get_span_context()

        return AgentEvent(
            event_type=event_type,
            trace_id=format(context.trace_id, "032x"),
            span_id=format(context.span_id, "016x"),
            correlation_id=correlation_id,
            tenant_id=uuid.UUID(str(tenant_id)),
            session_id=uuid.UUID(str(session_id)) if session_id else None,
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            role=role,
            skill_id=skill_id,
            payload=body,
            duration_ms=duration_ms,
            outcome=outcome,
        )

    async def emit(
        self, event_type: EventType, *, tenant_id: uuid.UUID | str, **kwargs: Any
    ) -> AgentEvent:
        """Build, record and enqueue one event.

        Returns the validated envelope so callers can assert on it. Raises if
        the event is malformed; never raises because publication failed.
        """
        event = self.build(event_type, tenant_id=tenant_id, **kwargs)

        # Always recorded, even with no broker: the span event and the log line
        # are what make events observable in production today.
        trace.get_current_span().add_event(
            event.event_type.value,
            attributes={
                "event.id": str(event.event_id),
                "event.ref": event.event_ref,
                "event.outcome": event.outcome,
                "tenant.id": str(event.tenant_id),
            },
        )
        logger.info(
            "agent_event",
            event_type=event.event_type.value,
            event_ref=event.event_ref,
            event_id=str(event.event_id),
            tenant_id=str(event.tenant_id),
            session_id=str(event.session_id) if event.session_id else None,
            trace_id=event.trace_id,
            outcome=event.outcome,
        )

        self._enqueue(event)
        return event

    def _enqueue(self, event: AgentEvent) -> None:
        payload = json.dumps(event.model_dump(mode="json")).encode()
        item = (
            events_topic(str(event.tenant_id)),
            message_key(str(event.tenant_id), str(event.session_id or "")),
            payload,
        )
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            # Losing an event is bad; losing the meeting is worse.
            self.dropped += 1
            logger.warning(
                "event_queue_full",
                dropped_total=self.dropped,
                event_type=event.event_type.value,
            )

    async def _drain(self) -> None:
        while True:
            topic, key, payload = await self._queue.get()
            try:
                await self._producer.send(topic, key=key, value=payload)
            except Exception as exc:  # noqa: BLE001 — never kills the worker
                logger.warning("event_publish_failed", topic=topic, error=str(exc))
            finally:
                self._queue.task_done()

    async def flush(self, timeout: float = 5.0) -> bool:
        """Wait for the queue to drain. Used by tests and graceful shutdown."""
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
