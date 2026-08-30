"""Tests for SKL-OIA-13 — RecordGoldenCandidates skill (L-02, §17.3).

Covers field extraction candidates, zero-edit-distance early return,
sufficiency override, PII redaction, evidence ref passthrough, prompt version
resolution, EVT-110 payload safety, and fire-and-forget error handling.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.events.catalog import EventType
from app.messaging.schemas import GoldenCandidate
from app.messaging.topics import GOLDEN_CANDIDATES, candidate_key
from app.skills.models import SkillContext, SkillMeta, TenantContext
from app.skills.record_golden_candidates import RecordGoldenCandidates

pytestmark = pytest.mark.unit

TENANT = str(uuid.uuid4())
SESSION = str(uuid.uuid4())


def _meta() -> SkillMeta:
    return SkillMeta(skill_id="SKL-OIA-13", name="record_golden_candidates")


def _context(
    *,
    field_name="company_name",
    extracted_value="Acme Inc",
    admin_final_value="Acme Corp",
    edit_distance=0.25,
    classification="KEY",
    evidence_ref="recording:r1:10.0-15.5",
    candidate_type="field_extraction",
    prompt_id="oia.extract_fields",
    session_id=None,
    tenant_id=None,
) -> SkillContext:
    return SkillContext(
        input_prompt="",
        tenant_context=TenantContext(
            tenant_id=tenant_id or TENANT,
            user_id="system",
            role="ADMIN",
        ),
        input_context={
            "candidate_type": candidate_type,
            "session_id": session_id or SESSION,
            "field_name": field_name,
            "extracted_value": extracted_value,
            "admin_final_value": admin_final_value,
            "edit_distance": edit_distance,
            "classification": classification,
            "evidence_ref": evidence_ref,
            "prompt_id": prompt_id,
        },
        correlation_id="corr-test-1",
    )


class FakeProducer:
    """Records Kafka publishes without a real broker."""

    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, topic: str, *, key: str, value: bytes) -> bool:
        self.sent.append({"topic": topic, "key": key, "value": value})
        return True


class FakeEmitter:
    """Records emitted events without Kafka."""

    def __init__(self):
        self.events: list[dict] = []

    async def emit(
        self,
        event_type,
        *,
        tenant_id,
        correlation_id,
        session_id=None,
        skill_id=None,
        payload=None,
        **kwargs,
    ):
        self.events.append(
            {
                "event_type": event_type,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
                "session_id": session_id,
                "skill_id": skill_id,
                "payload": payload or {},
            }
        )


class FakeRedis:
    """Simulates Redis hash reads for prompt version lookup."""

    def __init__(self, data=None):
        self._data = data or {}

    def keys_for(self, tenant_id):
        return _FakeKeys(tenant_id)

    @property
    def client(self):
        return self

    async def hget(self, key, field):
        return self._data.get(f"{key}:{field}")


class _FakeKeys:
    def __init__(self, tenant_id):
        self._tenant = tenant_id

    def session(self, session_id):
        return f"oia:v1:{self._tenant}:session:{session_id}"


# ── AC-2: field extraction candidate emitted ────────────────────────


class TestFieldExtractionCandidate:
    @pytest.fixture
    def producer(self):
        return FakeProducer()

    @pytest.fixture
    def emitter(self):
        return FakeEmitter()

    @pytest.fixture
    def skill(self, producer, emitter):
        return RecordGoldenCandidates(
            _meta(), producer=producer, emitter=emitter, redis=None
        )

    async def test_field_extraction_candidate_emitted(self, skill, producer, emitter):
        result = await skill.run(_context())

        assert result.output["candidates_emitted"] == 1
        assert result.output["dlq_count"] == 0

        assert len(producer.sent) == 1
        msg = producer.sent[0]
        assert msg["topic"] == GOLDEN_CANDIDATES.name
        assert msg["key"] == candidate_key(TENANT, "oia.extract_fields")

        envelope = json.loads(msg["value"])
        candidate = envelope["payload"]
        assert candidate["field_name"] == "company_name"
        assert candidate["classification"] == "KEY"
        assert candidate["edit_distance"] == 0.25
        assert candidate["accepted_without_edit"] is False

    async def test_evt110_emitted(self, skill, emitter):
        await skill.run(_context())

        assert len(emitter.events) == 1
        evt = emitter.events[0]
        assert evt["event_type"] == EventType.GOLDEN_CANDIDATE_RECORDED
        assert evt["skill_id"] == "SKL-OIA-13"


# ── AC-2: zero edit distance emits nothing ──────────────────────────


async def test_no_candidate_on_zero_edit_distance():
    producer = FakeProducer()
    emitter = FakeEmitter()
    skill = RecordGoldenCandidates(
        _meta(), producer=producer, emitter=emitter, redis=None
    )
    ctx = _context(edit_distance=0)
    result = await skill.run(ctx)

    assert result.output["candidates_emitted"] == 0
    assert result.output["dlq_count"] == 0
    assert len(producer.sent) == 0
    assert len(emitter.events) == 0


async def test_negative_edit_distance_emits_nothing():
    producer = FakeProducer()
    skill = RecordGoldenCandidates(_meta(), producer=producer)
    ctx = _context(edit_distance=-0.1)
    result = await skill.run(ctx)
    assert result.output["candidates_emitted"] == 0


# ── AC-3: sufficiency override ──────────────────────────────────────


async def test_sufficiency_override_emits_candidate():
    producer = FakeProducer()
    emitter = FakeEmitter()
    skill = RecordGoldenCandidates(
        _meta(), producer=producer, emitter=emitter, redis=None
    )
    ctx = _context(candidate_type="sufficiency_override", edit_distance=0)
    result = await skill.run(ctx)

    assert result.output["candidates_emitted"] == 1

    envelope = json.loads(producer.sent[0]["value"])
    candidate = envelope["payload"]
    assert candidate["prompt_id"] == "oia.sufficiency"
    assert candidate["classification"] == "KEY"
    assert candidate["edit_distance"] == 1.0


# ── AC-4: redaction precedes capture ────────────────────────────────


async def test_redaction_precedes_capture():
    """PII in extracted/final values must be redacted in the candidate."""
    producer = FakeProducer()
    skill = RecordGoldenCandidates(_meta(), producer=producer)
    ctx = _context(
        extracted_value="Call me at 555-867-5309",
        admin_final_value="Call me at 555-123-4567",
        edit_distance=0.3,
    )
    result = await skill.run(ctx)
    assert result.output["candidates_emitted"] == 1

    envelope = json.loads(producer.sent[0]["value"])
    candidate = envelope["payload"]
    assert "555-867-5309" not in candidate["extracted_value"]
    assert "555-123-4567" not in candidate["admin_final_value"]


# ── AC-4: evidence ref is a ref string, not text ────────────────────


async def test_evidence_ref_not_text():
    """Candidate carries a ref string, never raw text content."""
    producer = FakeProducer()
    skill = RecordGoldenCandidates(_meta(), producer=producer)
    ctx = _context(evidence_ref="recording:rec-42:10.0-20.5")
    await skill.run(ctx)

    envelope = json.loads(producer.sent[0]["value"])
    assert envelope["payload"]["input_evidence_ref"] == "recording:rec-42:10.0-20.5"


# ── Prompt version resolution ───────────────────────────────────────


async def test_prompt_version_resolved_from_redis():
    redis = FakeRedis(
        {
            f"oia:v1:{TENANT}:session:{SESSION}:prompt_versions": json.dumps(
                {"oia.extract_fields": "v3.1"}
            ),
        }
    )
    producer = FakeProducer()
    skill = RecordGoldenCandidates(_meta(), producer=producer, redis=redis)
    result = await skill.run(_context())

    assert result.prompt_version == "v3.1"

    envelope = json.loads(producer.sent[0]["value"])
    assert envelope["payload"]["prompt_version"] == "v3.1"


async def test_prompt_version_fallback_on_missing():
    redis = FakeRedis({})
    producer = FakeProducer()
    skill = RecordGoldenCandidates(_meta(), producer=producer, redis=redis)
    result = await skill.run(_context())

    assert result.prompt_version == "unknown"


async def test_prompt_version_fallback_without_redis():
    producer = FakeProducer()
    skill = RecordGoldenCandidates(_meta(), producer=producer, redis=None)
    result = await skill.run(_context())
    assert result.prompt_version == "unknown"


# ── EVT-110 payload safety ──────────────────────────────────────────


async def test_evt110_payload_has_no_values():
    """EVT-110 must carry ONLY prompt_id, prompt_version, edit_distance."""
    emitter = FakeEmitter()
    producer = FakeProducer()
    skill = RecordGoldenCandidates(
        _meta(), producer=producer, emitter=emitter, redis=None
    )
    await skill.run(_context())

    payload = emitter.events[0]["payload"]
    assert set(payload.keys()) == {"prompt_id", "prompt_version", "edit_distance"}
    assert "extracted_value" not in payload
    assert "admin_final_value" not in payload
    assert "value" not in payload


# ── Fire-and-forget: skill never raises ─────────────────────────────


class BrokenProducer:
    async def send(self, *args, **kwargs):
        raise ConnectionError("Kafka is down")


async def test_skill_never_raises_on_publish_failure():
    skill = RecordGoldenCandidates(
        _meta(), producer=BrokenProducer(), emitter=None, redis=None
    )
    result = await skill.run(_context())
    assert result.output["candidates_emitted"] == 1
    assert result.output["dlq_count"] == 1


async def test_skill_never_raises_on_internal_error():
    """Even a catastrophic bug returns a result with dlq_count."""
    skill = RecordGoldenCandidates(_meta(), producer=None, emitter=None, redis=None)
    ctx = _context()
    ctx.input_context["edit_distance"] = "not-a-number"
    result = await skill.run(ctx)
    assert result.output["dlq_count"] == 1


# ── Topic helpers ───────────────────────────────────────────────────


def test_candidate_key_format():
    key = candidate_key("tenant-1", "oia.extract_fields")
    assert key == "tenant-1:oia.extract_fields"


def test_golden_candidates_topic_config():
    assert GOLDEN_CANDIDATES.name == "onboarding.golden-dataset.candidates"
    assert GOLDEN_CANDIDATES.retention_ms == 30 * 24 * 60 * 60 * 1000


# ── GoldenCandidate model ──────────────────────────────────────────


def test_golden_candidate_model_validates():
    gc = GoldenCandidate(
        prompt_id="oia.extract_fields",
        prompt_version="v1",
        field_name="company_name",
        input_evidence_ref="recording:r1:10.0-15.0",
        extracted_value="Acme",
        admin_final_value="ACME Inc",
        edit_distance=0.5,
        classification="KEY",
        accepted_without_edit=False,
    )
    assert gc.edit_distance == 0.5
    assert gc.classification == "KEY"


def test_golden_candidate_rejects_bad_classification():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GoldenCandidate(
            prompt_id="x",
            prompt_version="v1",
            field_name="f",
            input_evidence_ref="r",
            extracted_value="a",
            admin_final_value="b",
            edit_distance=0.1,
            classification="INVALID",
            accepted_without_edit=False,
        )
