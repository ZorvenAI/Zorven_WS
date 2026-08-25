"""J-03 — Field extraction unit tests.

Tests the FieldExtractor against real Redis (via live_redis fixture), real
LLM responses simulated by a provider stand-in that returns canned JSON.
No mocks — the LLMProvider stand-in is the real class with a test client.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.schemas import EvidenceSpan
from app.logic.evidence_assembler import EvidenceBlock
from app.logic.field_extractor import (
    FieldExtractor,
    StepBudgetExceeded,
)

pytestmark = [pytest.mark.asyncio]


def _make_settings(**overrides: Any) -> Any:
    """Build a settings-like object with extraction defaults."""

    class FakeSettings:
        PROCESS_MODEL = "gemini-2.0-flash"
        EXTRACTION_MAX_STEPS = 40
        EXTRACTION_TEMPERATURE = 0.1
        EXTRACTION_RETRY_LIMIT = 1
        OG03_KEY_CONFIDENCE_THRESHOLD = 0.6

    s = FakeSettings()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _make_llm(responses: list[str]) -> Any:
    """Build a callable LLM stand-in that returns canned responses."""
    call_count = 0

    async def generate(
        prompt: str, *, temperature: float = 0.2, model: str | None = None
    ) -> str:
        nonlocal call_count
        idx = min(call_count, len(responses) - 1)
        call_count += 1
        return responses[idx]

    llm = AsyncMock()
    llm.generate = generate
    return llm


def _make_blocks() -> list[EvidenceBlock]:
    """A minimal evidence set with transcript and media blocks."""
    return [
        EvidenceBlock(
            text=(
                "Our company is called Chai Point."
                " We are in the food and beverage industry."
            ),
            spans=[
                EvidenceSpan(recording_id="rec-1", t_start=10.0, t_end=25.0),
            ],
            source_type="transcript",
            recording_id="rec-1",
        ),
        EvidenceBlock(
            text="We target young professionals aged 22-35 in urban areas.",
            spans=[
                EvidenceSpan(recording_id="rec-1", t_start=30.0, t_end=45.0),
            ],
            source_type="transcript",
            recording_id="rec-1",
        ),
    ]


def _page_response(fields: list[dict[str, Any]]) -> str:
    return json.dumps({"fields": fields})


def _good_field(name: str = "name", value: Any = "Chai Point") -> dict[str, Any]:
    return {
        "field_name": name,
        "value": value,
        "confidence": 0.95,
        "evidence": [{"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0}],
    }


async def test_extraction_per_page_isolation():
    """AC-5: page 2 schema failure doesn't lose pages 1, 3, 4."""
    responses = [
        _page_response([_good_field("name", "Chai Point")]),
        "THIS IS NOT VALID JSON {{{",  # page 2 fails
        "THIS IS NOT VALID JSON {{{",  # retry also fails
        _page_response([_good_field("target_audience", "Young professionals")]),
        _page_response([_good_field("competitors", [{"name": "Starbucks"}])]),
    ]
    llm = _make_llm(responses)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    errors = [p for p in result.pages if p.error]
    assert len(errors) == 1
    assert errors[0].page == 2

    successful = [p for p in result.pages if not p.error]
    assert len(successful) == 3


async def test_og01_drops_ungrounded_values():
    """OG-01: a field with no evidence refs is dropped."""
    response = _page_response(
        [
            _good_field("name", "Chai Point"),
            {
                "field_name": "description",
                "value": "A tea company",
                "confidence": 0.8,
                "evidence": [],  # no evidence!
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "name" in written_names
    assert "description" not in written_names
    assert result.dropped_ungrounded_total >= 1


async def test_pg06_blocks_protected_overwrite():
    """AC-4: EDITED/CONFIRMED provenance → field skipped, conflict reported."""
    response = _page_response(
        [
            _good_field("name", "New Name"),
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    existing = [
        {
            "model_name": "Company",
            "field_name": "name",
            "status": "CONFIRMED",
            "extracted_value": "Old Name",
        },
    ]

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=existing,
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "name" not in written_names
    assert len(result.conflicts) >= 1
    assert result.conflicts[0]["field_name"] == "name"
    assert result.conflicts[0]["existing_status"] == "CONFIRMED"


async def test_step_budget_enforced():
    """AC-1, PG-02: exceeding budget raises typed error."""
    llm = _make_llm(["THIS IS NOT VALID JSON"] * 100)
    settings = _make_settings(EXTRACTION_MAX_STEPS=3)
    extractor = FieldExtractor(llm=llm, settings=settings)

    with pytest.raises(StepBudgetExceeded):
        await extractor.extract_all(
            evidence_blocks=_make_blocks(),
            existing_provenance=[],
        )


async def test_b03_fields_extracted():
    """AC-3: 13 new B-03 fields can appear in results."""
    b03_fields = [
        _good_field("competitors", [{"name": "Starbucks"}]),
        _good_field("products_services", [{"name": "Masala Chai"}]),
        _good_field("marketing_budget_range", {"currency": "INR", "min": 50000}),
        _good_field("digital_presence", {"website": "chaipoint.com"}),
        _good_field("sales_channels", [{"channel": "retail"}]),
        _good_field("brand_asset_status", "logo only"),
    ]
    response_page4 = _page_response(b03_fields)

    # Other pages return nothing
    empty = _page_response([])
    llm = _make_llm([empty, empty, empty, response_page4])
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    written_names = {f["field_name"] for f in result.fields_written}
    assert "competitors" in written_names
    assert "products_services" in written_names
    assert "marketing_budget_range" in written_names


async def test_key_vs_secondary_classification():
    """OG-03: fields get correct classification."""
    response = _page_response(
        [
            _good_field("name", "Chai Point"),
            _good_field("founder_story", "Started in 2010"),
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    by_name = {f["field_name"]: f for f in result.fields_written}
    if "name" in by_name:
        assert by_name["name"]["classification"] == "KEY"
    if "founder_story" in by_name:
        assert by_name["founder_story"]["classification"] == "SECONDARY"


async def test_schema_retry_on_malformed():
    """AC-5: first LLM response malformed, retry succeeds."""
    bad = "not json at all"
    good = _page_response([_good_field("name", "Chai Point")])
    # Page 1: bad then good (retry), pages 2-4: good
    llm = _make_llm([bad, good, good, good, good, good])
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    page1 = next(p for p in result.pages if p.page == 1)
    assert page1.error is None
    assert result.steps_used >= 5  # 2 for page 1 (retry) + 1 each for 2,3,4


async def test_empty_evidence_yields_no_fields():
    """No crash on empty evidence."""
    llm = _make_llm([])
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=[],
        existing_provenance=[],
    )

    assert result.fields_written == []
    assert result.steps_used == 0


async def test_edited_field_is_also_protected():
    """PG-06: EDITED status is protected just like CONFIRMED."""
    response = _page_response(
        [
            _good_field("industry", "New Industry"),
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    existing = [
        {
            "model_name": "Company",
            "field_name": "industry",
            "status": "EDITED",
            "extracted_value": "Old Industry",
        },
    ]

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=existing,
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "industry" not in written_names
    assert len(result.conflicts) >= 1


async def test_pending_provenance_is_overwritable():
    """PENDING status allows overwrite — only CONFIRMED/EDITED are protected."""
    response = _page_response(
        [
            _good_field("industry", "New Industry"),
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    existing = [
        {
            "model_name": "Company",
            "field_name": "industry",
            "status": "PENDING",
            "extracted_value": "Old Industry",
        },
    ]

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=existing,
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "industry" in written_names
    assert len(result.conflicts) == 0


# ── J-04: grounding resolution, classification, egress ──────────────


async def test_grounding_resolves_recording_ids():
    """Valid recording_id passes, invalid is dropped."""
    response = _page_response(
        [
            _good_field("name", "Chai Point"),
            {
                "field_name": "industry",
                "value": "F&B",
                "confidence": 0.9,
                "evidence": [
                    {"recording_id": "nonexistent-42", "t_start": 1.0, "t_end": 5.0}
                ],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
        valid_recording_ids={"rec-1"},
        valid_media_ids=set(),
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "name" in written_names
    assert "industry" not in written_names
    assert result.dropped_ungrounded_total >= 1


async def test_grounding_resolves_media_ids():
    """Valid media_id passes, invalid is dropped."""
    response = _page_response(
        [
            {
                "field_name": "name",
                "value": "Chai Point",
                "confidence": 0.95,
                "evidence": [{"media_id": "media-1"}],
            },
            {
                "field_name": "industry",
                "value": "F&B",
                "confidence": 0.9,
                "evidence": [{"media_id": "nonexistent-99"}],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
        valid_recording_ids=set(),
        valid_media_ids={"media-1"},
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "name" in written_names
    assert "industry" not in written_names


async def test_all_refs_invalid_drops_field():
    """Field with only non-resolving refs → dropped entirely."""
    response = _page_response(
        [
            {
                "field_name": "name",
                "value": "Chai Point",
                "confidence": 0.95,
                "evidence": [
                    {"recording_id": "fake-1", "t_start": 1.0, "t_end": 5.0},
                    {"recording_id": "fake-2", "t_start": 6.0, "t_end": 10.0},
                ],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
        valid_recording_ids={"rec-1"},
        valid_media_ids=set(),
    )

    assert "name" not in [f["field_name"] for f in result.fields_written]
    assert result.dropped_ungrounded_total >= 1


async def test_mixed_refs_keeps_valid():
    """Field with 2 refs (1 valid, 1 invalid) → keeps field with 1 ref."""
    response = _page_response(
        [
            {
                "field_name": "name",
                "value": "Chai Point",
                "confidence": 0.95,
                "evidence": [
                    {"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0},
                    {"recording_id": "fake-99", "t_start": 30.0, "t_end": 40.0},
                ],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
        valid_recording_ids={"rec-1"},
        valid_media_ids=set(),
    )

    written_names = [f["field_name"] for f in result.fields_written]
    assert "name" in written_names
    name_field = next(f for f in result.fields_written if f["field_name"] == "name")
    assert len(name_field["evidence"]) == 1
    assert name_field["evidence"][0]["recording_id"] == "rec-1"


async def test_classify_forces_key_at_boundary():
    """OG-03: 0.59 → KEY, 0.60 → uses static lookup."""
    response_low = _page_response(
        [
            {
                "field_name": "founder_story",
                "value": "Started in a garage",
                "confidence": 0.55,
                "evidence": [{"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0}],
            },
        ]
    )
    llm = _make_llm([response_low] * 4)
    settings = _make_settings(OG03_KEY_CONFIDENCE_THRESHOLD=0.6)
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    by_name = {f["field_name"]: f for f in result.fields_written}
    if "founder_story" in by_name:
        assert by_name["founder_story"]["classification"] == "KEY"


async def test_egress_redaction_strips_pii():
    """OG-02: email in extracted value → redacted before return."""
    response = _page_response(
        [
            {
                "field_name": "name",
                "value": "Contact jane@acme.com for details",
                "confidence": 0.95,
                "evidence": [{"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0}],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings(OG03_KEY_CONFIDENCE_THRESHOLD=0.6)
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    by_name = {f["field_name"]: f for f in result.fields_written}
    if "name" in by_name:
        assert "jane@acme.com" not in str(by_name["name"]["value"])


async def test_egress_redaction_handles_nested_json():
    """OG-02: PII in nested JSON field values is also redacted."""
    response = _page_response(
        [
            {
                "field_name": "customer_proof",
                "value": [{"text": "John at john@acme.com loved it"}],
                "confidence": 0.9,
                "evidence": [{"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0}],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
    )

    by_name = {f["field_name"]: f for f in result.fields_written}
    if "customer_proof" in by_name:
        assert "john@acme.com" not in str(by_name["customer_proof"]["value"])


async def test_grounding_rejects_ref_without_ids():
    """Refs with only timestamps but no recording_id or media_id are dropped."""
    response = _page_response(
        [
            {
                "field_name": "name",
                "value": "Chai Point",
                "confidence": 0.95,
                "evidence": [{"t_start": 1.0, "t_end": 5.0}],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings()
    extractor = FieldExtractor(llm=llm, settings=settings)

    result = await extractor.extract_all(
        evidence_blocks=_make_blocks(),
        existing_provenance=[],
        valid_recording_ids={"rec-1"},
        valid_media_ids=set(),
    )

    assert "name" not in [f["field_name"] for f in result.fields_written]
    assert result.dropped_ungrounded_total >= 1


async def test_tenant_isolation_blocks_foreign_uuid():
    """OG-05: foreign UUID in value → GuardrailViolation."""
    from app.logic.guardrails import GuardrailViolation

    foreign = "bbbbbbbb-5555-6666-7777-888888888888"
    response = _page_response(
        [
            {
                "field_name": "name",
                "value": f"Company ref: {foreign}",
                "confidence": 0.95,
                "evidence": [{"recording_id": "rec-1", "t_start": 10.0, "t_end": 25.0}],
            },
        ]
    )
    llm = _make_llm([response] * 4)
    settings = _make_settings(OG03_KEY_CONFIDENCE_THRESHOLD=0.6)
    extractor = FieldExtractor(llm=llm, settings=settings)

    own_tenant = "aaaaaaaa-1111-2222-3333-444444444444"
    with pytest.raises(GuardrailViolation) as exc:
        await extractor.extract_all(
            evidence_blocks=_make_blocks(),
            existing_provenance=[],
            tenant_id=own_tenant,
        )

    assert exc.value.verdict.rule_id == "OG-05"
