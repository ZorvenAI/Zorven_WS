"""J-06 — SKL-OIA-12 autogen_strategy_identity skill tests."""

from __future__ import annotations

from typing import Any

import pytest

from app.skills.autogen_strategy_identity import AutogenStrategyIdentity
from app.skills.models import SkillContext, SkillMeta, TenantContext

pytestmark = pytest.mark.unit


class FakeBackend:
    """Stand-in that records calls and returns configurable results."""

    _DEFAULT_RESULT: dict[str, Any] = {"success": True}

    def __init__(
        self,
        *,
        strategy_result: dict[str, Any] | None = _DEFAULT_RESULT,
        identity_result: dict[str, Any] | None = _DEFAULT_RESULT,
        strategy_error: Exception | None = None,
        identity_error: Exception | None = None,
        configured: bool = True,
    ) -> None:
        self._strategy_result = (
            dict(strategy_result) if strategy_result else strategy_result
        )
        self._identity_result = (
            dict(identity_result) if identity_result else identity_result
        )
        self._strategy_error = strategy_error
        self._identity_error = identity_error
        self.configured = configured

    async def generate_brand_strategy(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any] | None:
        if self._strategy_error:
            raise self._strategy_error
        return self._strategy_result

    async def generate_brand_identity(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any] | None:
        if self._identity_error:
            raise self._identity_error
        return self._identity_result


def _meta() -> SkillMeta:
    return SkillMeta(skill_id="SKL-OIA-12", name="autogen_strategy_identity")


def _ctx(
    company_id: int | None = 42,
    auto_strategy: bool = True,
    auto_identity: bool = True,
) -> SkillContext:
    input_context: dict[str, Any] = {
        "auto_generate_strategy": auto_strategy,
        "auto_generate_identity": auto_identity,
    }
    if company_id is not None:
        input_context["company_id"] = company_id

    return SkillContext(
        input_prompt="generate",
        tenant_context=TenantContext(
            tenant_id="aaaaaaaa-1111-2222-3333-444444444444",
            user_id="u-1",
            role="ADMIN",
            session_id="bbbbbbbb-1111-2222-3333-444444444444",
        ),
        input_context=input_context,
    )


async def test_skill_generates_both():
    """Happy path: both strategy and identity generated."""
    backend = FakeBackend()
    skill = AutogenStrategyIdentity(_meta(), backend=backend)

    result = await skill.run(_ctx())

    assert result.output["generated"] == ["brand_strategy", "brand_identity"]
    assert result.output["strategy_ref"] == {"type": "company_fields"}
    assert result.output["identity_ref"] == {"type": "company_fields"}


async def test_skill_no_company_id():
    """Missing company_id → reason returned, no crash."""
    backend = FakeBackend()
    skill = AutogenStrategyIdentity(_meta(), backend=backend)

    result = await skill.run(_ctx(company_id=None))

    assert result.output["generated"] == []
    assert result.output["reason"] == "no_company_id"


async def test_skill_backend_not_configured():
    """Unconfigured backend → reason returned."""
    backend = FakeBackend(configured=False)
    skill = AutogenStrategyIdentity(_meta(), backend=backend)

    result = await skill.run(_ctx())

    assert result.output["generated"] == []
    assert result.output["reason"] == "backend_not_configured"


async def test_skill_no_backend():
    """No backend at all → reason returned."""
    skill = AutogenStrategyIdentity(_meta(), backend=None)

    result = await skill.run(_ctx())

    assert result.output["generated"] == []
    assert result.output["reason"] == "backend_not_configured"


async def test_skill_partial_failure():
    """Strategy fails, identity succeeds → partial result."""
    backend = FakeBackend(strategy_error=RuntimeError("boom"))
    skill = AutogenStrategyIdentity(_meta(), backend=backend)

    result = await skill.run(_ctx())

    assert result.output["generated"] == ["brand_identity"]
    assert result.output["strategy_ref"] is None
    assert result.output["identity_ref"] == {"type": "company_fields"}


async def test_skill_strategy_only():
    """Identity disabled → only strategy generated."""
    backend = FakeBackend()
    skill = AutogenStrategyIdentity(_meta(), backend=backend)

    result = await skill.run(_ctx(auto_identity=False))

    assert result.output["generated"] == ["brand_strategy"]
    assert result.output["identity_ref"] is None
