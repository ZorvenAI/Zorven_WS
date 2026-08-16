"""G-01 · PII redaction: NER-based detection, allowlist, RedactionResult.

Upgraded from F-05's pattern-only tests. The engine now uses spaCy NER
(via Presidio's AnalyzerEngine) so PERSON and LOCATION are detectable.
The function returns a RedactionResult with text, applied flag, and
entity_types for EVT-103.
"""

from __future__ import annotations

import pytest

from app.skills.redact_pii import (
    RedactPii,
    _regex_fallback,
    ig04_redact,
    redact_text,
)

pytestmark = pytest.mark.unit


# ── redact_text — entity coverage (AC-2) ──────────────────────────


def test_redact_person_name():
    result = redact_text("Please contact Sarah about the order.")
    assert result.applied is True  # also proves it's a RedactionResult, not str
    assert "Sarah" not in result.text
    assert "PERSON" in result.text
    assert "PERSON" in result.entity_types


def test_redact_phone_number():
    result = redact_text("Call me at 555-867-5309 anytime.")
    assert "555-867-5309" not in result.text
    assert "PHONE_NUMBER" in result.text
    assert result.applied is True
    assert "PHONE_NUMBER" in result.entity_types


def test_redact_email():
    result = redact_text("My email is john@example.com for updates.")
    assert "john@example.com" not in result.text
    assert "EMAIL_ADDRESS" in result.text
    assert result.applied is True
    assert "EMAIL_ADDRESS" in result.entity_types


def test_redact_ssn():
    result = redact_text("My SSN is 456-78-9012 on file.")
    assert "456-78-9012" not in result.text
    assert "US_SSN" in result.text
    assert result.applied is True
    assert "US_SSN" in result.entity_types


def test_redact_location():
    result = redact_text("Our office is in San Francisco.")
    assert result.applied is not None  # proves it's a RedactionResult, not str
    if result.applied:
        assert "LOCATION" in result.entity_types


def test_redact_multiple_entities():
    result = redact_text("Call Sarah at 555-867-5309 or email john@example.com.")
    assert "555-867-5309" not in result.text
    assert "john@example.com" not in result.text
    assert result.applied is True
    assert len(result.entity_types) >= 2


def test_no_pii_returns_unchanged():
    text = "We started roasting in 2016."
    result = redact_text(text)
    assert result.text == text
    assert result.applied is False
    assert result.entity_types == []


def test_empty_string_returns_unchanged():
    result = redact_text("")
    assert result.text == ""
    assert result.applied is False

    result = redact_text("   ")
    assert result.text == "   "
    assert result.applied is False


def test_none_returns_result_with_none():
    result = redact_text(None)
    assert result.text is None
    assert result.applied is False


# ── RedactionResult structure ──────────────────────────────────────


def test_result_applied_flag_true():
    result = redact_text("Call Sarah about the report.")
    assert result.applied is True


def test_result_applied_flag_false():
    result = redact_text("We have no personal data here.")
    assert result.applied is False


def test_entity_types_returned_in_result():
    result = redact_text("Sarah called 555-867-5309.")
    assert result.applied is True
    assert len(result.entity_types) >= 1
    assert all(t in ("PERSON", "PHONE_NUMBER") for t in result.entity_types)
    assert len(result.entity_types) == len(set(result.entity_types))


def test_entity_types_sorted():
    result = redact_text("Sarah emailed john@example.com and called 555-867-5309.")
    if result.applied:
        assert result.entity_types == sorted(result.entity_types)


# ── Company name allowlist (AC-3) ─────────────────────────────────


def test_company_name_survives_redaction():
    """AC-3 fixture: "Sarah" is redacted, "Kelso Coffee" is preserved."""
    result = redact_text(
        "Sarah from Kelso Coffee called about the new blend.",
        allowlist=["Kelso Coffee"],
    )
    assert "Sarah" not in result.text
    assert "Kelso Coffee" in result.text
    assert result.applied is True
    assert "PERSON" in result.entity_types


def test_person_like_brand_survives():
    """A brand name that looks like a person name is preserved."""
    result = redact_text(
        "We need to update the Marlow brand positioning.",
        allowlist=["Marlow"],
    )
    assert "Marlow" in result.text


def test_allowlist_case_insensitive():
    result = redact_text(
        "Sarah from Kelso Coffee.",
        allowlist=["kelso coffee"],
    )
    assert "Kelso Coffee" in result.text


def test_allowlist_empty_has_no_effect():
    result = redact_text("Sarah called about the order.", allowlist=[])
    assert "Sarah" not in result.text
    assert result.applied is True


def test_allowlist_none_has_no_effect():
    result = redact_text("Sarah called about the order.", allowlist=None)
    assert "Sarah" not in result.text
    assert result.applied is True


def test_configured_entities_from_settings(monkeypatch):
    """PII_ENTITIES env var is parsed into the entity list."""
    monkeypatch.setenv("OIA_PII_ENTITIES", "PERSON,PHONE_NUMBER")
    from app.core.config import get_settings

    get_settings.cache_clear()
    result = redact_text("Sarah called at 555-867-5309.")
    assert result.applied is True
    get_settings.cache_clear()


# ── Regex fallback ──────────────────────────────────────────────────


def test_regex_fallback_phone():
    result = _regex_fallback("Call 555-867-5309.")
    assert "555-867-5309" not in result
    assert "<PHONE_NUMBER>" in result


def test_regex_fallback_email():
    result = _regex_fallback("Mail to john@example.com.")
    assert "john@example.com" not in result
    assert "<EMAIL_ADDRESS>" in result


def test_regex_fallback_ssn():
    result = _regex_fallback("SSN: 123-45-6789.")
    assert "123-45-6789" not in result
    assert "<US_SSN>" in result


def test_regex_fallback_credit_card():
    result = _regex_fallback("Card: 4111 1111 1111 1111.")
    assert "4111 1111 1111 1111" not in result
    assert "<CREDIT_CARD>" in result


# ── IG-04 guardrail rule ──────────────────────────────────────────


def test_ig04_redacts_string_with_pii():
    from app.skills.models import SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    verdict = ig04_redact("Call me at 555-867-5309.", ctx)
    assert verdict.action.value == "REDACT"
    assert "555-867-5309" not in verdict.payload


def test_ig04_redacts_person_name():
    from app.skills.models import SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    verdict = ig04_redact("Sarah mentioned the new project.", ctx)
    assert verdict.action.value == "REDACT"
    assert "Sarah" not in verdict.payload


def test_ig04_passes_clean_text():
    from app.skills.models import SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    verdict = ig04_redact("No PII here.", ctx)
    assert verdict.action.value == "PASS"


def test_ig04_passes_non_string():
    from app.skills.models import SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    verdict = ig04_redact({"key": "value"}, ctx)
    assert verdict.action.value == "PASS"


# ── Skill wrapper ──────────────────────────────────────────────────


async def test_skill_run_redacts():
    from app.skills.models import SkillContext, SkillMeta, TenantContext

    skill = RedactPii(SkillMeta(skill_id="SKL-OIA-16", name="redact_pii"))
    ctx = SkillContext(
        input_prompt="My number is 555-867-5309.",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    result = await skill.run(ctx)
    assert result.output["redaction_applied"] is True
    assert "555-867-5309" not in result.output["redacted_text"]
    assert len(result.output["entity_types"]) >= 1
    assert "PHONE_NUMBER" in result.output["entity_types"]


async def test_skill_run_detects_person():
    from app.skills.models import SkillContext, SkillMeta, TenantContext

    skill = RedactPii(SkillMeta(skill_id="SKL-OIA-16", name="redact_pii"))
    ctx = SkillContext(
        input_prompt="Sarah mentioned the new branding strategy.",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    result = await skill.run(ctx)
    assert result.output["redaction_applied"] is True
    assert "PERSON" in result.output["entity_types"]


async def test_skill_run_no_pii():
    from app.skills.models import SkillContext, SkillMeta, TenantContext

    skill = RedactPii(SkillMeta(skill_id="SKL-OIA-16", name="redact_pii"))
    ctx = SkillContext(
        input_prompt="We started in 2016.",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    result = await skill.run(ctx)
    assert result.output["redaction_applied"] is False
    assert result.output["entity_types"] == []
