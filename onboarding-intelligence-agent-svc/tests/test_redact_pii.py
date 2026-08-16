"""F-05 · PII redaction: SKL-OIA-16, IG-04, and the fallback.

Named test from the story:
``test_persisted_transcript_is_redacted`` — after a final with a phone
number in it, the buffered frame has ``<PHONE_NUMBER>``, not the digits.
That test lives in ``test_stt_pipeline.py`` because it needs the full
pipeline; these tests verify the redaction function in isolation.
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


# ── redact_text (the shared function) ───────────────────────────────


def test_redact_phone_number():
    text = "Call me at 555-867-5309 anytime."
    result = redact_text(text)
    assert "555-867-5309" not in result
    assert "PHONE_NUMBER" in result


def test_redact_email():
    text = "My email is john@example.com for updates."
    result = redact_text(text)
    assert "john@example.com" not in result
    assert "EMAIL_ADDRESS" in result


def test_redact_ssn():
    text = "My SSN is 456-78-9012 on file."
    result = redact_text(text)
    assert "456-78-9012" not in result
    assert "US_SSN" in result


def test_redact_multiple_entities():
    text = "Call 555-867-5309 or email john@example.com."
    result = redact_text(text)
    assert "555-867-5309" not in result
    assert "john@example.com" not in result


def test_no_pii_returns_unchanged():
    text = "We started roasting in 2016."
    assert redact_text(text) == text


def test_empty_string_returns_unchanged():
    assert redact_text("") == ""
    assert redact_text("   ") == "   "


def test_none_returns_none():
    assert redact_text(None) is None


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


# ── IG-04 guardrail rule ───────────────────────────────────────────


def test_ig04_redacts_string_with_pii():
    from app.skills.models import SkillContext, TenantContext

    ctx = SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    verdict = ig04_redact("Call me at 555-867-5309.", ctx)
    assert verdict.action.value == "REDACT"
    assert "555-867-5309" not in verdict.payload


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


async def test_skill_run_no_pii():
    from app.skills.models import SkillContext, SkillMeta, TenantContext

    skill = RedactPii(SkillMeta(skill_id="SKL-OIA-16", name="redact_pii"))
    ctx = SkillContext(
        input_prompt="We started in 2016.",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )
    result = await skill.run(ctx)
    assert result.output["redaction_applied"] is False
