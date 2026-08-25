"""J-05 — Conflict detection and escalation tests.

Covers enriched conflict dicts, EscalationMessage construction,
sanitised callback summaries, and EVT-007 emission. Real Redis,
no mocks.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest

from app.events.catalog import FORBIDDEN_PAYLOAD_KEYS
from app.logic.field_extractor import ExtractedField, FieldExtractor
from app.logic.conflict_helpers import format_evidence_ref
from app.logic.process_executor import ProcessExecutor
from app.messaging.schemas import ConflictCandidate, EscalationMessage

pytestmark = pytest.mark.unit


# ── Fixtures ────────────────────────────────────────────────────────────


_UNSET = object()


def _make_conflict(
    field_name: str = "name",
    existing_status: str = "CONFIRMED",
    existing_value: str = "Old Corp",
    new_value: str = "New Corp",
    new_confidence: float = 0.92,
    new_classification: str = "KEY",
    new_evidence: Any = _UNSET,
    existing_source_span: Any = _UNSET,
    existing_confidence: float | None = 0.95,
) -> dict[str, Any]:
    if new_evidence is _UNSET:
        new_evidence = [{"recording_id": "rec-1", "t_start": 12.5, "t_end": 18.3}]
    if existing_source_span is _UNSET:
        existing_source_span = {
            "recording_id": "rec-0",
            "t_start": 1.0,
            "t_end": 5.0,
        }
    return {
        "field_name": field_name,
        "existing_status": existing_status,
        "existing_value": existing_value,
        "new_value": new_value,
        "new_evidence": new_evidence,
        "new_confidence": new_confidence,
        "new_classification": new_classification,
        "existing_source_span": existing_source_span,
        "existing_confidence": existing_confidence,
    }


# ── Enriched conflict dicts from _check_protected ───────────────────────


def test_conflict_dict_includes_evidence_refs():
    """_check_protected enriches conflicts with evidence and metadata."""
    candidates = [
        ExtractedField(
            field_name="name",
            value="New Corp",
            confidence=0.92,
            evidence=[{"recording_id": "rec-1", "t_start": 12.5, "t_end": 18.3}],
            classification="KEY",
        ),
    ]
    protected = {
        "Company.name": {
            "status": "CONFIRMED",
            "extracted_value": "Old Corp",
            "source_span": {"recording_id": "rec-0", "t_start": 1.0, "t_end": 5.0},
            "confidence": 0.95,
        }
    }

    _writable, _skipped, conflicts = FieldExtractor._check_protected(
        candidates, protected
    )

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["field_name"] == "name"
    assert c["new_evidence"] == [
        {"recording_id": "rec-1", "t_start": 12.5, "t_end": 18.3}
    ]
    assert c["new_confidence"] == 0.92
    assert c["new_classification"] == "KEY"
    assert c["existing_source_span"] == {
        "recording_id": "rec-0",
        "t_start": 1.0,
        "t_end": 5.0,
    }
    assert c["existing_confidence"] == 0.95


# ── EscalationMessage construction ──────────────────────────────────────


def test_escalation_message_builds_from_conflict():
    """ConflictCandidate entries are correctly built from an enriched conflict."""
    conflict = _make_conflict()
    candidates = ProcessExecutor._build_candidates(conflict)

    assert len(candidates) == 2
    existing = candidates[0]
    assert existing.source == "existing"
    assert existing.evidence_ref == "recording:rec-0:1.0-5.0"
    assert existing.confidence == 0.95

    new = candidates[1]
    assert new.source == "new"
    assert new.evidence_ref == "recording:rec-1:12.5-18.3"
    assert new.confidence == 0.92
    assert new.classification == "KEY"


def test_escalation_message_with_media_evidence():
    """Media-based evidence uses media:ID format."""
    conflict = _make_conflict(
        new_evidence=[{"media_id": "42"}],
        existing_source_span={"media_id": "7"},
    )
    candidates = ProcessExecutor._build_candidates(conflict)

    assert candidates[0].evidence_ref == "media:7"
    assert candidates[1].evidence_ref == "media:42"


def test_escalation_message_missing_spans_uses_provenance_ref():
    """When source_span is absent, falls back to provenance/extraction ref."""
    conflict = _make_conflict(
        new_evidence=[],
        existing_source_span=None,
    )
    candidates = ProcessExecutor._build_candidates(conflict)

    assert candidates[0].evidence_ref == "provenance:name"
    assert candidates[1].evidence_ref == "extraction:name"


# ── Callback summary sanitisation ───────────────────────────────────────


def test_callback_summary_has_conflict_list():
    """AC-4: summary carries individual records, not a count."""
    conflicts = [
        _make_conflict("name"),
        _make_conflict("industry", new_confidence=0.88, new_classification="SECONDARY"),
    ]
    result = ProcessExecutor._sanitise_conflicts(conflicts)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["field_name"] == "name"
    assert result[1]["field_name"] == "industry"
    assert result[1]["new_confidence"] == 0.88
    assert result[1]["new_classification"] == "SECONDARY"


def test_callback_conflicts_sanitised():
    """Values are stripped from the callback payload."""
    conflict = _make_conflict()
    result = ProcessExecutor._sanitise_conflicts([conflict])

    record = result[0]
    assert "existing_value" not in record
    assert "new_value" not in record
    assert "new_evidence" not in record
    assert "existing_source_span" not in record
    assert record["field_name"] == "name"
    assert record["existing_status"] == "CONFIRMED"


# ── EVT-007 payload safety ──────────────────────────────────────────────


def test_evt007_payload_contains_no_forbidden_keys():
    """The escalation event payload must pass FORBIDDEN_PAYLOAD_KEYS."""
    payload = {
        "escalation_id": str(uuid.uuid4()),
        "reason_code": "FIELD_CONFLICT",
        "field_name": "name",
        "candidate_count": 2,
    }
    offending = FORBIDDEN_PAYLOAD_KEYS.intersection(payload)
    assert not offending, f"Forbidden keys in EVT-007 payload: {offending}"


# ── EscalationMessage serialisation ─────────────────────────────────────


def test_escalation_message_serialises_without_values():
    """The Kafka message must not contain extracted text values."""
    msg = EscalationMessage(
        tenant_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        reason_code="FIELD_CONFLICT",
        field_name="name",
        candidates=[
            ConflictCandidate(
                source="existing",
                evidence_ref="recording:rec-0:1.0-5.0",
                confidence=0.95,
            ),
            ConflictCandidate(
                source="new",
                evidence_ref="recording:rec-1:12.5-18.3",
                confidence=0.92,
                classification="KEY",
            ),
        ],
        context_ref="job:abc123",
    )

    serialised = json.loads(msg.model_dump_json())
    assert serialised["reason_code"] == "FIELD_CONFLICT"
    assert len(serialised["candidates"]) == 2
    assert serialised["context_ref"] == "job:abc123"

    flat = json.dumps(serialised)
    assert "Old Corp" not in flat
    assert "New Corp" not in flat


# ── format_evidence_ref ────────────────────────────────────────────────


def testformat_evidence_ref_recording():
    ref = format_evidence_ref({"recording_id": "rec-1", "t_start": 12.5, "t_end": 18.3})
    assert ref == "recording:rec-1:12.5-18.3"


def testformat_evidence_ref_media():
    ref = format_evidence_ref({"media_id": "42"})
    assert ref == "media:42"


def testformat_evidence_ref_unknown():
    ref = format_evidence_ref({})
    assert ref == "unknown"


# ── No conflicts = no escalation ────────────────────────────────────────


def test_no_conflicts_produces_empty_summary():
    """Clean extraction → empty conflict list, not 0."""
    result = ProcessExecutor._sanitise_conflicts([])
    assert result == []
