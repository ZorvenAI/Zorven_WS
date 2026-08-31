"""M-01 · PG-01 through PG-07 process guardrail tests."""

from __future__ import annotations

import pytest

from app.logic.guardrails import Action
from app.logic.process_guardrails import (
    pg01_plan_required,
    pg02_skill_allowlist,
    pg03_rbac,
    pg04_write_scope,
    pg05_prompt_pinning,
    pg06_field_protection,
    pg07_budget_guard,
)
from app.skills.models import SkillContext, TenantContext

pytestmark = pytest.mark.unit


def _ctx(**config: object) -> SkillContext:
    return SkillContext(
        input_prompt="test",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1"),
        config=dict(config),
    )


def _ctx_with_input(input_context: dict, **config: object) -> SkillContext:
    return SkillContext(
        input_prompt="test",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1"),
        input_context=input_context,
        config=dict(config),
    )


# ── PG-01 ────────────────────────────────────────────────


class TestPG01PlanRequired:
    def test_escalates_without_plan(self):
        ctx = _ctx()
        v = pg01_plan_required({}, ctx)
        assert v.action is Action.ESCALATE

    def test_passes_with_plan(self):
        ctx = _ctx(plan_emitted=True)
        v = pg01_plan_required({}, ctx)
        assert v.action is Action.PASS


# ── PG-02 ────────────────────────────────────────────────


class TestPG02SkillAllowlist:
    def test_passes_valid_skill(self):
        ctx = _ctx_with_input({"skill_id": "SKL-OIA-04"})
        v = pg02_skill_allowlist({}, ctx)
        assert v.action is Action.PASS

    def test_blocks_invalid_skill(self):
        ctx = _ctx_with_input({"skill_id": "SKL-OTHER-99"})
        v = pg02_skill_allowlist({}, ctx)
        assert v.action is Action.BLOCK

    def test_blocks_out_of_range(self):
        ctx = _ctx_with_input({"skill_id": "SKL-OIA-99"})
        v = pg02_skill_allowlist({}, ctx)
        assert v.action is Action.BLOCK

    def test_passes_when_no_skill_id(self):
        ctx = _ctx_with_input({})
        v = pg02_skill_allowlist({}, ctx)
        assert v.action is Action.PASS


# ── PG-03 ────────────────────────────────────────────────


class TestPG03RBAC:
    def test_always_passes(self):
        ctx = _ctx()
        v = pg03_rbac({}, ctx)
        assert v.action is Action.PASS


# ── PG-04 ────────────────────────────────────────────────


class TestPG04WriteScope:
    def test_blocks_without_tenant(self):
        ctx = SkillContext(
            input_prompt="test",
            tenant_context=TenantContext(tenant_id="", user_id="u-1"),
        )
        v = pg04_write_scope({}, ctx)
        assert v.action is Action.BLOCK

    def test_blocks_delete_operation(self):
        ctx = _ctx()
        v = pg04_write_scope({"operation": "DELETE"}, ctx)
        assert v.action is Action.BLOCK

    def test_passes_normal_write(self):
        ctx = _ctx()
        v = pg04_write_scope({"operation": "CREATE"}, ctx)
        assert v.action is Action.PASS


# ── PG-05 ────────────────────────────────────────────────


class TestPG05PromptPinning:
    def test_blocks_re_resolution_when_pinned(self):
        ctx = _ctx(
            prompt_versions={"oia.research_brief": "v1"},
            _prompt_re_resolve=True,
        )
        v = pg05_prompt_pinning({}, ctx)
        assert v.action is Action.BLOCK

    def test_passes_when_not_pinned(self):
        ctx = _ctx()
        v = pg05_prompt_pinning({}, ctx)
        assert v.action is Action.PASS

    def test_passes_when_no_re_resolve(self):
        ctx = _ctx(prompt_versions={"oia.research_brief": "v1"})
        v = pg05_prompt_pinning({}, ctx)
        assert v.action is Action.PASS


# ── PG-06 ────────────────────────────────────────────────


class TestPG06FieldProtection:
    def test_drops_protected_field(self):
        ctx = _ctx(protected_fields=["company_name", "tenant_id"])
        v = pg06_field_protection({"company_name": "Evil Corp"}, ctx)
        assert v.action is Action.DROP

    def test_passes_unprotected_field(self):
        ctx = _ctx(protected_fields=["company_name"])
        v = pg06_field_protection({"description": "test"}, ctx)
        assert v.action is Action.PASS

    def test_passes_when_no_protected_fields(self):
        ctx = _ctx()
        v = pg06_field_protection({"anything": "value"}, ctx)
        assert v.action is Action.PASS


# ── PG-07 ────────────────────────────────────────────────


class TestPG07BudgetGuard:
    def test_blocks_over_budget(self):
        ctx = _ctx(_token_count=50_000, _token_budget=40_000)
        v = pg07_budget_guard({}, ctx)
        assert v.action is Action.BLOCK

    def test_passes_under_budget(self):
        ctx = _ctx(_token_count=20_000, _token_budget=40_000)
        v = pg07_budget_guard({}, ctx)
        assert v.action is Action.PASS

    def test_passes_when_no_budget(self):
        ctx = _ctx(_token_count=999_999)
        v = pg07_budget_guard({}, ctx)
        assert v.action is Action.PASS
