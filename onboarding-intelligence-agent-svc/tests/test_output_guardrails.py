"""J-04 / M-01 — Output guardrail chain rules (OG-02 through OG-05).

Tests the chain-compatible rule functions that run on the OUTPUT layer.
"""

from __future__ import annotations

import pytest

from app.logic.guardrails import Action
from app.logic.output_guardrails import (
    og02_egress_redact,
    og03_confidence_gate,
    og04_sampled_judge,
    og05_tenant_isolation,
)
from app.skills.models import SkillContext, TenantContext

pytestmark = pytest.mark.unit


def _ctx(tenant_id: str = "aaaaaaaa-1111-2222-3333-444444444444") -> SkillContext:
    return SkillContext(
        input_prompt="test",
        tenant_context=TenantContext(tenant_id=tenant_id, role="ADMIN"),
    )


def test_og02_redacts_pii_in_payload():
    """Chain rule: PII in a string payload → REDACT verdict."""
    verdict = og02_egress_redact("Email me at john@example.com", _ctx())

    assert verdict.action is Action.REDACT
    assert "john@example.com" not in verdict.payload


def test_og02_passes_clean_payload():
    """No PII in the payload → PASS verdict."""
    verdict = og02_egress_redact("No personal info here", _ctx())

    assert verdict.action is Action.PASS
    assert verdict.payload == "No personal info here"


def test_og02_redacts_dict_payload():
    """Dict payload with PII in a string value → REDACT with cleaned dict."""
    payload = {"name": "John", "email": "john@example.com", "count": 42}
    verdict = og02_egress_redact(payload, _ctx())

    assert verdict.action is Action.REDACT
    assert "john@example.com" not in str(verdict.payload)


def test_og02_passes_clean_dict():
    """Dict payload without PII → PASS."""
    payload = {"name": "Acme Corp", "industry": "Technology"}
    verdict = og02_egress_redact(payload, _ctx())

    assert verdict.action is Action.PASS


def test_og02_redacts_nested_values():
    """PII buried in nested dicts/lists is caught."""
    payload = {
        "testimonials": [
            {"text": "Great service!", "contact": "jane@acme.com"},
        ],
    }
    verdict = og02_egress_redact(payload, _ctx())

    assert verdict.action is Action.REDACT
    assert "jane@acme.com" not in str(verdict.payload)


def test_og05_blocks_foreign_tenant():
    """Foreign UUID in output → BLOCK verdict with detail."""
    own = "aaaaaaaa-1111-2222-3333-444444444444"
    foreign = "bbbbbbbb-5555-6666-7777-888888888888"

    verdict = og05_tenant_isolation(f"Some data from tenant {foreign}", _ctx(own))

    assert verdict.action is Action.BLOCK
    assert foreign in verdict.detail


def test_og05_passes_own_tenant():
    """Own tenant_id in output → PASS (not a violation)."""
    own = "aaaaaaaa-1111-2222-3333-444444444444"

    verdict = og05_tenant_isolation(f"Data for tenant {own}", _ctx(own))

    assert verdict.action is Action.PASS


def test_og05_passes_no_uuids():
    """No UUID-shaped strings → PASS."""
    verdict = og05_tenant_isolation("Just plain text", _ctx())

    assert verdict.action is Action.PASS


def test_og05_scans_nested_dicts():
    """UUIDs buried in nested structures are still detected."""
    own = "aaaaaaaa-1111-2222-3333-444444444444"
    foreign = "cccccccc-9999-8888-7777-666666666666"

    payload = {"data": {"nested": {"value": f"ref={foreign}"}}}
    verdict = og05_tenant_isolation(payload, _ctx(own))

    assert verdict.action is Action.BLOCK


def test_og05_scans_lists():
    """UUIDs in list items are detected."""
    own = "aaaaaaaa-1111-2222-3333-444444444444"
    foreign = "dddddddd-1111-2222-3333-eeeeeeeeeeee"

    payload = ["item1", f"tenant-{foreign}", "item3"]
    verdict = og05_tenant_isolation(payload, _ctx(own))

    assert verdict.action is Action.BLOCK


# ── OG-03 ────────────────────────────────────────────────


def _ctx_with_config(**config: object) -> SkillContext:
    return SkillContext(
        input_prompt="test",
        tenant_context=TenantContext(
            tenant_id="aaaaaaaa-1111-2222-3333-444444444444", role="ADMIN"
        ),
        config=dict(config),
    )


def test_og03_forces_key_below_threshold():
    """Low confidence → forced to KEY."""
    ctx = _ctx_with_config(_og03_threshold=0.6)
    payload = {"confidence": 0.3, "classification": "SUPPLEMENTARY"}
    verdict = og03_confidence_gate(payload, ctx)
    assert verdict.action is Action.REDACT
    assert verdict.payload["classification"] == "KEY"


def test_og03_passes_above_threshold():
    """High confidence → PASS."""
    ctx = _ctx_with_config(_og03_threshold=0.6)
    payload = {"confidence": 0.9, "classification": "SUPPLEMENTARY"}
    verdict = og03_confidence_gate(payload, ctx)
    assert verdict.action is Action.PASS


def test_og03_passes_without_confidence():
    """No confidence field → PASS."""
    ctx = _ctx_with_config(_og03_threshold=0.6)
    payload = {"classification": "KEY"}
    verdict = og03_confidence_gate(payload, ctx)
    assert verdict.action is Action.PASS


def test_og03_passes_non_dict():
    """Non-dict payload → PASS."""
    ctx = _ctx_with_config(_og03_threshold=0.6)
    verdict = og03_confidence_gate("just text", ctx)
    assert verdict.action is Action.PASS


# ── OG-04 ────────────────────────────────────────────────


def test_og04_stashes_payload_when_sampled():
    """When sampled, the payload is stashed for async judge."""
    ctx = _ctx_with_config(_og04_sample_selected=True)
    payload = {"text": "some output"}
    verdict = og04_sampled_judge(payload, ctx)
    assert verdict.action is Action.PASS
    assert ctx.config["_og04_payload"] == payload


def test_og04_does_not_stash_when_not_sampled():
    """When not sampled, nothing is stashed."""
    ctx = _ctx_with_config(_og04_sample_selected=False)
    payload = {"text": "some output"}
    verdict = og04_sampled_judge(payload, ctx)
    assert verdict.action is Action.PASS
    assert "_og04_payload" not in ctx.config
