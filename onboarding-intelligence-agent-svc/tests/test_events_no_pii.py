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


def test_empty_payload_is_fine():
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
