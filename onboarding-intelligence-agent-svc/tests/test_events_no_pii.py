"""AC-2 — the envelope is the one in the design, and it keeps PII off the stream.

The event stream reaches observability tooling under a different access model
than the tenant-scoped transcript store. §12.2 is explicit that EVT-103 carries
entity *types* and never entity values or segment text: `["PERSON",
"PHONE_NUMBER"]` tells an operator that redaction fired and on what; the values
stay in the store.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.events.catalog import (
    EVENT_IDS,
    AgentEvent,
    EventType,
    PIILeakError,
    assert_no_pii,
)

pytestmark = pytest.mark.unit

TENANT = uuid.uuid4()


def envelope(**overrides) -> dict:
    base = dict(
        event_type=EventType.AGENT_INVOKED,
        trace_id="0af7651916cd43dd8448eb211c80319c",
        span_id="b7ad6b7169203331",
        correlation_id="corr-1",
        tenant_id=TENANT,
    )
    base.update(overrides)
    return base


def test_envelope_validates():
    event = AgentEvent(**envelope())
    assert event.agent_id == "onboarding-intelligence"
    assert event.schema_version == "1.0"
    assert event.outcome == "SUCCESS"
    assert event.timestamp.tzinfo is not None


@pytest.mark.parametrize(
    "missing", ["trace_id", "span_id", "correlation_id", "tenant_id"]
)
def test_envelope_rejects_missing_correlation_fields(missing):
    """AC-2: a payload that fails validation raises rather than emitting."""
    fields = envelope()
    del fields[missing]
    with pytest.raises(ValidationError):
        AgentEvent(**fields)


@pytest.mark.parametrize("blank", ["", "   "])
def test_envelope_rejects_blank_trace_ids(blank):
    """An event that cannot be joined to its request is not auditable."""
    with pytest.raises(ValidationError):
        AgentEvent(**envelope(trace_id=blank))


def test_occurred_at_is_accepted_as_an_alias_for_timestamp():
    """AC-2 says occurred_at; Design §12's model says timestamp, and AC-2
    defers to §12. Both names work so neither document is wrong in practice."""
    from datetime import datetime, timezone

    when = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    assert AgentEvent(**envelope(occurred_at=when)).timestamp == when


def test_event_type_enum_complete():
    """All 22 event IDs from §12 are present in the enum."""
    ids = set(EVENT_IDS.values())
    expected = {f"EVT-{n:03d}" for n in range(1, 13)} | {
        f"EVT-{n}" for n in range(101, 111)
    }
    assert ids == expected, sorted(expected.symmetric_difference(ids))
    assert len(ids) == 22


def test_enum_has_24_members_for_22_ids():
    """EVT-011 and EVT-102 each name a pair, so members exceed IDs by two."""
    assert len(list(EventType)) == 24
    assert EVENT_IDS[EventType.AGENT_CIRCUIT_OPENED] == "EVT-011"
    assert EVENT_IDS[EventType.AGENT_CIRCUIT_CLOSED] == "EVT-011"
    assert EVENT_IDS[EventType.RECORDING_STARTED] == "EVT-102"
    assert EVENT_IDS[EventType.RECORDING_STOPPED] == "EVT-102"


def test_every_enum_member_maps_to_an_id():
    """A member without an ID would break event_ref at runtime."""
    for member in EventType:
        assert member in EVENT_IDS, member


def test_event_ref_resolves():
    event = AgentEvent(**envelope(event_type=EventType.TRANSCRIPT_SEGMENT_FINALIZED))
    assert event.event_ref == "EVT-103"


@pytest.mark.parametrize(
    "forbidden",
    ["text", "transcript", "segment_text", "entity_values", "email", "extracted_value"],
)
def test_payload_carrying_pii_is_rejected(forbidden):
    with pytest.raises(PIILeakError, match=forbidden):
        assert_no_pii(EventType.TRANSCRIPT_SEGMENT_FINALIZED, {forbidden: "anything"})


def test_evt_103_shape_from_the_design_is_accepted():
    """§12.2's own example: recording_id, seq, redaction_applied, entity_types."""
    payload = {
        "recording_id": "r_01",
        "seq": 814,
        "redaction_applied": True,
        "entity_types": ["PERSON", "PHONE_NUMBER"],
    }
    assert_no_pii(EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload)
    event = AgentEvent(
        **envelope(event_type=EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload=payload)
    )
    assert event.payload["entity_types"] == ["PERSON", "PHONE_NUMBER"]
    assert "text" not in event.payload


def test_entity_types_allowed_while_entity_values_are_not():
    """The distinction §12.2 draws, asserted directly."""
    assert_no_pii(EventType.TRANSCRIPT_SEGMENT_FINALIZED, {"entity_types": ["PERSON"]})
    with pytest.raises(PIILeakError):
        assert_no_pii(
            EventType.TRANSCRIPT_SEGMENT_FINALIZED, {"entity_values": ["Ada"]}
        )


def test_empty_payload_is_fine():  # weak-assert: ok — assert_no_pii raises
    # The call is the assertion: assert_no_pii raises PIILeakError on a
    # violation, so reaching the next line is the pass condition.
    assert_no_pii(EventType.AGENT_INVOKED, {})


def test_outcome_is_constrained_to_the_design_values():
    for outcome in ("SUCCESS", "FAILURE", "BLOCKED", "DEGRADED"):
        assert AgentEvent(**envelope(outcome=outcome)).outcome == outcome
    with pytest.raises(ValidationError):
        AgentEvent(**envelope(outcome="MAYBE"))


def test_event_serialises_to_json_for_kafka():
    """The emitter publishes model_dump(mode='json'); UUIDs must survive it."""
    import json

    event = AgentEvent(**envelope(session_id=uuid.uuid4()))
    body = json.loads(json.dumps(event.model_dump(mode="json")))
    assert body["tenant_id"] == str(TENANT)
    assert body["event_type"] == "agent.invoked"


# ── Regression cover for PR #532 review findings ─────────────────────────


@pytest.mark.parametrize("field", ["trace_id", "span_id"])
def test_all_zero_correlation_ids_are_rejected(field):
    """OpenTelemetry's invalid context must never reach the audit stream.

    Review finding: outside an active span OTel returns all-zero ids. Such an
    event validates structurally but can never be joined to anything, so the
    stream would fill with events that look correlated and are not.
    """
    zeros = "0" * (32 if field == "trace_id" else 16)
    with pytest.raises(ValidationError, match="invalid context"):
        AgentEvent(**envelope(**{field: zeros}))


def test_emitter_never_emits_all_zero_ids_outside_a_span():
    """A background task must still produce a correlatable event.

    With an SDK provider installed the emitter starts a real span; without
    one — a script or a worker that forgot to configure telemetry — it
    synthesises unique ids rather than crashing or emitting 000….
    """
    from app.events.emitter import EventEmitter
    from app.messaging.producer import KafkaProducer

    emitter = EventEmitter(KafkaProducer.__new__(KafkaProducer))
    first = emitter.build(
        EventType.AGENT_COMPLETED, tenant_id=TENANT, correlation_id="corr-bg-1"
    )
    second = emitter.build(
        EventType.AGENT_COMPLETED, tenant_id=TENANT, correlation_id="corr-bg-2"
    )

    for event in (first, second):
        assert set(event.trace_id) != {"0"}
        assert set(event.span_id) != {"0"}
        assert len(event.trace_id) == 32
        assert len(event.span_id) == 16

    # Unique per event, so the stream stays groupable rather than collapsing
    # every background event onto one placeholder trace.
    assert first.trace_id != second.trace_id


def test_emitter_joins_a_real_span_when_the_sdk_is_configured():
    """The path that matters in production: a real, joinable trace."""
    from opentelemetry import trace as ot
    from opentelemetry.sdk.trace import TracerProvider

    from app.events.emitter import EventEmitter
    from app.messaging.producer import KafkaProducer

    if not isinstance(ot.get_tracer_provider(), TracerProvider):
        ot.set_tracer_provider(TracerProvider())

    emitter = EventEmitter(KafkaProducer.__new__(KafkaProducer))
    tracer = ot.get_tracer("test")
    with tracer.start_as_current_span("caller") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        event = emitter.build(
            EventType.AGENT_INVOKED, tenant_id=TENANT, correlation_id="corr-live"
        )

    assert event.trace_id == expected


# ── F-01 · EVT-101 ───────────────────────────────────────────────────


# ── G-01 · EVT-103 emission tests ─────────────────────────────────


def test_evt103_with_person_redaction_accepted():
    """G-01 AC-4: entity types are carried, never entity values."""
    payload = {
        "recording_id": "r_meeting_01",
        "seq": 42,
        "redaction_applied": True,
        "entity_types": ["PERSON"],
    }
    assert_no_pii(EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload)
    event = AgentEvent(
        **envelope(event_type=EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload=payload)
    )
    assert event.payload["entity_types"] == ["PERSON"]
    assert event.payload["redaction_applied"] is True
    assert "text" not in event.payload


def test_evt103_with_multiple_entity_types():
    payload = {
        "recording_id": "r_02",
        "seq": 100,
        "redaction_applied": True,
        "entity_types": ["EMAIL_ADDRESS", "PERSON", "PHONE_NUMBER"],
    }
    assert_no_pii(EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload)
    event = AgentEvent(
        **envelope(event_type=EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload=payload)
    )
    assert len(event.payload["entity_types"]) == 3


def test_evt103_no_redaction_applied():
    """When no PII found, redaction_applied is False and entity_types is empty."""
    payload = {
        "recording_id": "r_03",
        "seq": 7,
        "redaction_applied": False,
        "entity_types": [],
    }
    assert_no_pii(EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload)
    event = AgentEvent(
        **envelope(event_type=EventType.TRANSCRIPT_SEGMENT_FINALIZED, payload=payload)
    )
    assert event.payload["redaction_applied"] is False
    assert event.payload["entity_types"] == []


def test_evt103_rejects_text_in_payload():
    """The segment text must never appear in the event stream."""
    with pytest.raises(PIILeakError):
        assert_no_pii(
            EventType.TRANSCRIPT_SEGMENT_FINALIZED,
            {
                "recording_id": "r_04",
                "seq": 5,
                "text": "Sarah mentioned the merger.",
            },
        )


def test_evt103_rejects_entity_values_in_payload():
    """Entity values (the actual PII text) must never appear."""
    with pytest.raises(PIILeakError):
        assert_no_pii(
            EventType.TRANSCRIPT_SEGMENT_FINALIZED,
            {
                "recording_id": "r_05",
                "seq": 5,
                "entity_values": ["Sarah", "555-867-5309"],
            },
        )


def test_evt103_serialises_for_kafka():
    """The event round-trips through JSON without losing entity_types."""
    import json

    payload = {
        "recording_id": "r_06",
        "seq": 814,
        "redaction_applied": True,
        "entity_types": ["LOCATION", "PERSON"],
    }
    event = AgentEvent(
        **envelope(
            event_type=EventType.TRANSCRIPT_SEGMENT_FINALIZED,
            payload=payload,
            session_id=uuid.uuid4(),
        )
    )
    body = json.loads(json.dumps(event.model_dump(mode="json")))
    assert body["payload"]["entity_types"] == ["LOCATION", "PERSON"]
    assert body["payload"]["redaction_applied"] is True
    assert "text" not in body["payload"]


# ── F-01 · EVT-101 ───────────────────────────────────────────────────


def test_evt101_carries_hash_not_name():
    """The card's named case, on the agent's side of the contract.

    Django builds and emits EVT-101 (the consent endpoint is §10.2's), and its
    own test asserts the payload it produces. This asserts the other half: that
    the catalogue would *refuse* the name if a future caller attached it here.
    Two teams, one contract, and the structural guard is what keeps them from
    drifting apart quietly.
    """
    with pytest.raises(PIILeakError):
        assert_no_pii(EventType.CONSENT_VERIFIED, {"subject_name": "Asha Kalyani"})


def test_evt101_accepts_the_hashed_shape():
    """The control. A guard that rejected everything would pass the test above
    and block the event it exists to permit.

    Built into a real envelope rather than stopping at "assert_no_pii did not
    raise", following test_evt_103's shape in this file. Not raising is a
    claim about the guard; surviving into an AgentEvent with the hash intact
    and no name anywhere is the claim that matters.
    """
    payload = {
        "consent_id": "c-1",
        "method": "VERBAL_RECORDED",
        "subject_name_hash": "9f" * 32,
    }
    assert_no_pii(EventType.CONSENT_VERIFIED, payload)

    event = AgentEvent(
        **envelope(event_type=EventType.CONSENT_VERIFIED, payload=payload)
    )

    assert event.payload["subject_name_hash"] == "9f" * 32
    assert "subject_name" not in event.payload


# ── L-02 · EVT-110 ─────────────────────────────────────────────────


def test_evt110_payload_passes_assert_no_pii():
    """AC-4: the permitted fields pass the PII guard."""
    payload = {
        "prompt_id": "oia.extract_fields",
        "prompt_version": "v3.1",
        "edit_distance": 0.34,
    }
    assert_no_pii(EventType.GOLDEN_CANDIDATE_RECORDED, payload)

    event = AgentEvent(
        **envelope(event_type=EventType.GOLDEN_CANDIDATE_RECORDED, payload=payload)
    )
    assert event.payload["prompt_id"] == "oia.extract_fields"
    assert event.payload["edit_distance"] == 0.34
    assert "extracted_value" not in event.payload
    assert "admin_final_value" not in event.payload


@pytest.mark.parametrize(
    "forbidden_key",
    ["extracted_value", "admin_final_value", "value"],
)
def test_evt110_with_values_fails_assert_no_pii(forbidden_key):
    """AC-4: forbidden fields raise PIILeakError on EVT-110."""
    payload = {
        "prompt_id": "oia.extract_fields",
        "prompt_version": "v1",
        "edit_distance": 0.5,
        forbidden_key: "some secret data",
    }
    with pytest.raises(PIILeakError, match=forbidden_key):
        assert_no_pii(EventType.GOLDEN_CANDIDATE_RECORDED, payload)
