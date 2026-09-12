"""Event type catalogue and envelope (Design §12).

The enum is populated with the **full** EVT-001…012 and EVT-101…110 set now,
even though most are unused until later epics. A-03's technical note explains
why: a complete enum makes the later stories one-line additions, and it makes
``tests/test_events_no_pii.py`` meaningful from week 2 rather than week 9.

Note on counting. §12 lists 22 event **IDs**, but two of them name a pair —
EVT-011 is ``agent.circuit.opened`` / ``.closed`` and EVT-102 is
``onboarding.recording.started`` / ``.stopped``. The enum is keyed by
``event_type`` string, so it has 24 members covering 22 IDs. Both counts are
asserted in the tests so neither can drift.

The event stream is a **lower-trust surface than the transcript store** — it
fans out to observability tooling under a different access model. EVT-103
therefore carries entity *types* and never entity values or segment text.
:func:`assert_no_pii` enforces that structurally.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

AGENT_ID = "onboarding-intelligence"
SCHEMA_VERSION = "1.0"


class EventType(StrEnum):
    """Every event this service can emit (Design §12.1 and §12.2)."""

    # ── §12.1 Mandatory fleet events ─────────────────────────
    AGENT_INVOKED = "agent.invoked"  # EVT-001
    AGENT_PLAN_CREATED = "agent.plan.created"  # EVT-002
    AGENT_SKILL_INVOKED = "agent.skill.invoked"  # EVT-003
    AGENT_GUARDRAIL_TRIGGERED = "agent.guardrail.triggered"  # EVT-004
    AGENT_TOOL_CALLED = "agent.tool.called"  # EVT-005
    AGENT_MEMORY_WRITTEN = "agent.memory.written"  # EVT-006
    AGENT_ESCALATED = "agent.escalated"  # EVT-007
    AGENT_COMPLETED = "agent.completed"  # EVT-008
    AGENT_FAILED = "agent.failed"  # EVT-009
    AGENT_RETRIED = "agent.retried"  # EVT-010
    AGENT_CIRCUIT_OPENED = "agent.circuit.opened"  # EVT-011
    AGENT_CIRCUIT_CLOSED = "agent.circuit.closed"  # EVT-011
    AGENT_RATE_LIMITED = "agent.rate_limited"  # EVT-012
    AGENT_OUTBOX_OVERFLOW = "agent.outbox.overflow"  # EVT-013

    # ── §12.2 Domain events ──────────────────────────────────
    CONSENT_VERIFIED = "onboarding.consent.verified"  # EVT-101
    RECORDING_STARTED = "onboarding.recording.started"  # EVT-102
    RECORDING_STOPPED = "onboarding.recording.stopped"  # EVT-102
    TRANSCRIPT_SEGMENT_FINALIZED = "onboarding.transcript.segment.finalized"  # 103
    SUFFICIENCY_SIGNAL = "onboarding.sufficiency.signal"  # EVT-104
    FOLLOWUP_SUGGESTED = "onboarding.followup.suggested"  # EVT-105
    MEDIA_CAPTURED_ANALYZED = "onboarding.media.captured.analyzed"  # EVT-106
    COVERAGE_UPDATED = "onboarding.coverage.updated"  # EVT-107
    PROCESSING_COMPLETED = "onboarding.processing.completed"  # EVT-108
    PROVENANCE_REVIEWED = "onboarding.provenance.reviewed"  # EVT-109
    GOLDEN_CANDIDATE_RECORDED = "onboarding.golden.candidate.recorded"  # EVT-110


#: event_type → the §12 ID it realises. Two IDs map from two members each.
EVENT_IDS: dict[EventType, str] = {
    EventType.AGENT_INVOKED: "EVT-001",
    EventType.AGENT_PLAN_CREATED: "EVT-002",
    EventType.AGENT_SKILL_INVOKED: "EVT-003",
    EventType.AGENT_GUARDRAIL_TRIGGERED: "EVT-004",
    EventType.AGENT_TOOL_CALLED: "EVT-005",
    EventType.AGENT_MEMORY_WRITTEN: "EVT-006",
    EventType.AGENT_ESCALATED: "EVT-007",
    EventType.AGENT_COMPLETED: "EVT-008",
    EventType.AGENT_FAILED: "EVT-009",
    EventType.AGENT_RETRIED: "EVT-010",
    EventType.AGENT_CIRCUIT_OPENED: "EVT-011",
    EventType.AGENT_CIRCUIT_CLOSED: "EVT-011",
    EventType.AGENT_RATE_LIMITED: "EVT-012",
    EventType.AGENT_OUTBOX_OVERFLOW: "EVT-013",
    EventType.CONSENT_VERIFIED: "EVT-101",
    EventType.RECORDING_STARTED: "EVT-102",
    EventType.RECORDING_STOPPED: "EVT-102",
    EventType.TRANSCRIPT_SEGMENT_FINALIZED: "EVT-103",
    EventType.SUFFICIENCY_SIGNAL: "EVT-104",
    EventType.FOLLOWUP_SUGGESTED: "EVT-105",
    EventType.MEDIA_CAPTURED_ANALYZED: "EVT-106",
    EventType.COVERAGE_UPDATED: "EVT-107",
    EventType.PROCESSING_COMPLETED: "EVT-108",
    EventType.PROVENANCE_REVIEWED: "EVT-109",
    EventType.GOLDEN_CANDIDATE_RECORDED: "EVT-110",
}

Outcome = Literal["SUCCESS", "FAILURE", "BLOCKED", "DEGRADED"]

#: Payload keys that must never appear on the event stream. The stream reaches
#: observability tooling under a different access model than the tenant-scoped
#: transcript store, so text and entity values stay out of it entirely.
FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "text",
        "transcript",
        "segment",
        "segment_text",
        "content",
        "entity_values",
        "entities",
        "raw",
        "audio",
        "email",
        "phone",
        "phone_number",
        "address",
        "full_name",
        "subject_name",
        "value",
        "extracted_value",
        "admin_final_value",
    }
)


class PIILeakError(ValueError):
    """Raised when a payload carries a field the event stream must not see."""


def assert_no_pii(event_type: EventType, payload: dict[str, Any]) -> None:
    """Reject payload shapes that would put PII on the event stream.

    Structural, not semantic: it catches a caller reaching for ``text`` or
    ``entity_values``. Semantic redaction of free text is SKL-OIA-16's job in
    F-05 — this is the guard that stops an unredacted field being attached to
    an event in the first place.
    """
    offending = sorted(FORBIDDEN_PAYLOAD_KEYS.intersection(payload))
    if offending:
        raise PIILeakError(
            f"{event_type.value} payload carries forbidden key(s) {offending}. "
            "The event stream records that redaction fired and on what — "
            "entity types, counts, ids — never values or text (Design §12.2)."
        )


class AgentEvent(BaseModel):
    """The fleet-standard envelope (Design §12).

    Note on naming: A-03 AC-2 lists the field as ``occurred_at`` while §12's
    model calls it ``timestamp``. AC-2 defers to "the AgentEvent Pydantic
    envelope specified in Design §12", so ``timestamp`` is authoritative and
    ``occurred_at`` is accepted as an alias.
    """

    model_config = {"populate_by_name": True}

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: EventType
    schema_version: str = SCHEMA_VERSION
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="occurred_at"
    )
    trace_id: str
    span_id: str
    correlation_id: str
    tenant_id: uuid.UUID
    agent_id: str = AGENT_ID
    session_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    role: str | None = None
    skill_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = None
    outcome: Outcome = "SUCCESS"

    @field_validator("trace_id", "span_id", "correlation_id")
    @classmethod
    def _must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "must not be empty — an event without correlation cannot be "
                "joined to the request that caused it"
            )
        return v

    @field_validator("trace_id", "span_id")
    @classmethod
    def _must_not_be_the_invalid_context(cls, v: str) -> str:
        """Reject OpenTelemetry's all-zero ids.

        Emitting outside an active span yields the invalid context, whose ids
        are all zeros. Such an event validates structurally but can never be
        joined to anything, so the audit stream would fill with events that
        look correlated and are not. The emitter starts a span rather than
        letting this happen; this is the guard for any other caller.
        """
        if set(v) == {"0"}:
            raise ValueError(
                "is OpenTelemetry's invalid context (all zeros) — the event "
                "was built outside an active span and would be "
                "uncorrelatable. Start a span, or use EventEmitter, which "
                "does it for you."
            )
        return v

    @property
    def event_ref(self) -> str:
        """The §12 ID this event realises, e.g. ``EVT-103``."""
        return EVENT_IDS[self.event_type]
