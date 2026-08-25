"""J-04 — Output guardrail chain rules (OG-02, OG-05).

Tests the chain-compatible rule functions that run on the OUTPUT layer.
"""

from __future__ import annotations

import pytest

from app.logic.guardrails import Action
from app.logic.output_guardrails import og02_egress_redact, og05_tenant_isolation
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
