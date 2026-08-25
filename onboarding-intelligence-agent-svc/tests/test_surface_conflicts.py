"""J-05 — SKL-OIA-14 surface_conflicts_and_escalate skill tests."""

from __future__ import annotations

import pytest

from app.skills.models import SkillContext, SkillMeta, SkillResult, TenantContext
from app.skills.surface_conflicts_and_escalate import SurfaceConflictsAndEscalate

pytestmark = pytest.mark.unit


def _meta() -> SkillMeta:
    return SkillMeta(skill_id="SKL-OIA-14", name="surface_conflicts_and_escalate")


def _ctx(conflicts: list | None = None) -> SkillContext:
    return SkillContext(
        input_prompt="escalate",
        tenant_context=TenantContext(
            tenant_id="aaaaaaaa-1111-2222-3333-444444444444",
            user_id="u-1",
            role="ADMIN",
            session_id="bbbbbbbb-1111-2222-3333-444444444444",
        ),
        input_context={"conflicts": conflicts or []},
    )


async def test_skill_returns_escalation_payload():
    """SKL-OIA-14 builds escalation items from provided conflicts."""
    conflicts = [
        {
            "field_name": "name",
            "existing_status": "CONFIRMED",
            "existing_value": "Old Corp",
            "new_value": "New Corp",
            "new_evidence": [{"recording_id": "rec-1", "t_start": 12.5, "t_end": 18.3}],
            "new_confidence": 0.92,
            "new_classification": "KEY",
            "existing_source_span": {
                "recording_id": "rec-0",
                "t_start": 1.0,
                "t_end": 5.0,
            },
            "existing_confidence": 0.95,
        },
        {
            "field_name": "industry",
            "existing_status": "EDITED",
            "existing_value": "Tech",
            "new_value": "SaaS",
            "new_evidence": [{"media_id": "42"}],
            "new_confidence": 0.88,
            "new_classification": "KEY",
            "existing_source_span": None,
            "existing_confidence": None,
        },
    ]

    skill = SurfaceConflictsAndEscalate(_meta())
    result = await skill.run(_ctx(conflicts))

    assert isinstance(result, SkillResult)
    assert result.output["escalation_count"] == 2
    assert result.output["severity"] == "MEDIUM"
    assert len(result.output["items"]) == 2

    first = result.output["items"][0]
    assert first["field_name"] == "name"
    assert first["reason_code"] == "FIELD_CONFLICT"
    assert first["candidate_count"] == 2
    assert "escalation_id" in first


async def test_skill_empty_conflicts():
    """No conflicts → clean return with zero count."""
    skill = SurfaceConflictsAndEscalate(_meta())
    result = await skill.run(_ctx([]))

    assert result.output["escalation_count"] == 0
    assert result.output["items"] == []


async def test_skill_high_severity_above_two():
    """More than 2 conflicts → HIGH severity."""
    conflicts = [
        {
            "field_name": f"field_{i}",
            "existing_status": "CONFIRMED",
            "existing_value": f"old_{i}",
            "new_value": f"new_{i}",
            "new_evidence": [],
            "new_confidence": 0.9,
            "new_classification": "KEY",
            "existing_source_span": None,
            "existing_confidence": None,
        }
        for i in range(3)
    ]

    skill = SurfaceConflictsAndEscalate(_meta())
    result = await skill.run(_ctx(conflicts))

    assert result.output["severity"] == "HIGH"
    assert result.output["escalation_count"] == 3
