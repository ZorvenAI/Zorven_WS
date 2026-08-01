"""AC-2 — guardrails run in a fixed order and cannot be skipped.

A-06 proves the ordering, not the rules: every §5 rule is registered as a
recording no-op, and these tests assert that IG runs before the prompt is
built, PG around execution, and OG before the result is returned — for the
streaming case, before *each* chunk.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from app.logic.guardrails import (
    INPUT_RULES,
    OUTPUT_RULES,
    PROCESS_RULES,
    Action,
    GuardrailChain,
    GuardrailViolation,
    Layer,
    Verdict,
)
from app.rbac.engine import RBACEngine, Role
from app.skills.base import BaseSkill, StreamingSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult, TenantContext
from app.skills.registry import SkillRegistry

pytestmark = pytest.mark.unit


def context(role: str = "ADMIN") -> SkillContext:
    return SkillContext(
        input_prompt="hello",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role=role),
        input_context={"skill_id": "SKL-OIA-01"},
        correlation_id="corr-1",
    )


class RecordingSkill(BaseSkill):
    """Records when its body ran, relative to the guardrail calls."""

    def __init__(self, meta: SkillMeta, log: list[str]) -> None:
        super().__init__(meta)
        self.log = log

    async def run(self, ctx: SkillContext) -> SkillResult:
        self.log.append("SKILL")
        return SkillResult(skill_id=self.meta.skill_id, output={"ok": True})


class RecordingStream(StreamingSkill):
    def __init__(self, meta: SkillMeta, chunks: int = 3) -> None:
        super().__init__(meta)
        self.chunks = chunks

    async def stream(self, ctx: SkillContext) -> AsyncIterator[dict[str, Any]]:
        for index in range(self.chunks):
            yield {"seq": index}


@pytest.fixture
def chain() -> GuardrailChain:
    return GuardrailChain()


def test_every_section_5_rule_is_registered(chain):
    """The chain is complete from the first commit, even as no-ops."""
    assert chain.rules(Layer.INPUT) == INPUT_RULES
    assert chain.rules(Layer.PROCESS) == PROCESS_RULES
    assert chain.rules(Layer.OUTPUT) == OUTPUT_RULES
    assert len(INPUT_RULES) == 10
    assert len(PROCESS_RULES) == 8
    assert len(OUTPUT_RULES) == 6


async def test_hook_ordering(chain):
    """IG before the skill, PG around it, OG after — by recorded call order."""
    log: list[str] = []
    meta = SkillMeta(skill_id="SKL-OIA-01", name="research_business")
    registry = SkillRegistry(chain=chain, rbac=RBACEngine())
    skill = RecordingSkill(meta, log)
    registry._by_id[meta.skill_id] = skill
    registry._meta[meta.skill_id] = meta

    original_evaluate = chain.evaluate

    def tracking(layer, payload, ctx):
        log.append(layer.value)
        return original_evaluate(layer, payload, ctx)

    chain.evaluate = tracking  # type: ignore[method-assign]

    await registry.execute("SKL-OIA-01", context())

    assert log == ["IG", "PG", "SKILL", "OG"], log


async def test_streaming_og_per_yield(chain):
    """Output guardrails evaluate each yielded chunk, not only the final one."""
    meta = SkillMeta(skill_id="SKL-OIA-04", name="analyze_transcript_stream")
    registry = SkillRegistry(chain=chain, rbac=RBACEngine())
    skill = RecordingStream(meta, chunks=4)
    registry._by_id[meta.skill_id] = skill
    registry._meta[meta.skill_id] = meta

    chunks = [c async for c in registry.execute_stream("SKL-OIA-04", context())]

    assert len(chunks) == 4
    og_calls = [c for c in chain.calls if c[0] is Layer.OUTPUT]
    # Six OG rules, evaluated once per chunk.
    assert len(og_calls) == 4 * len(OUTPUT_RULES)


async def test_streaming_chunks_are_evaluated_before_they_are_yielded(chain):
    """A chunk already sent to the browser cannot be recalled."""
    meta = SkillMeta(skill_id="SKL-OIA-04", name="analyze_transcript_stream")
    registry = SkillRegistry(chain=chain, rbac=RBACEngine())
    registry._by_id[meta.skill_id] = RecordingStream(meta, chunks=3)
    registry._meta[meta.skill_id] = meta

    seen = 0
    async for _ in registry.execute_stream("SKL-OIA-04", context()):
        seen += 1
        og_calls = len([c for c in chain.calls if c[0] is Layer.OUTPUT])
        assert og_calls == seen * len(OUTPUT_RULES)


def test_a_blocking_rule_stops_the_chain(chain):
    """BLOCK raises: a blocked payload must not reach the next stage."""

    def blocker(payload, ctx):
        return Verdict(rule_id="IG-02", action=Action.BLOCK, detail="scam pattern")

    chain.register(Layer.INPUT, "IG-02", blocker)

    with pytest.raises(GuardrailViolation) as exc:
        chain.evaluate(Layer.INPUT, {"x": 1}, context())

    assert exc.value.verdict.rule_id == "IG-02"


def test_a_rule_may_transform_the_payload(chain):
    """REDACT and TRUNCATE hand the next rule the modified payload."""

    def redactor(payload, ctx):
        return Verdict(rule_id="IG-04", action=Action.REDACT, payload={"x": "***"})

    chain.register(Layer.INPUT, "IG-04", redactor)
    assert chain.evaluate(Layer.INPUT, {"x": "secret"}, context()) == {"x": "***"}


def test_registering_a_rule_replaces_the_no_op(chain):
    """M-01 fills bodies in through this door without changing the order."""
    before = chain.rules(Layer.INPUT)

    def rule(payload, ctx):
        return Verdict(rule_id="IG-01")

    chain.register(Layer.INPUT, "IG-01", rule)
    assert chain.rules(Layer.INPUT) == [r for r in before if r != "IG-01"] + ["IG-01"]
    assert len(chain.rules(Layer.INPUT)) == len(before)


async def test_a_skill_cannot_be_reached_except_through_the_registry():
    """AC-2: BaseSkill is not callable, so there is no bypass to reach for."""
    meta = SkillMeta(skill_id="SKL-OIA-01", name="research_business")
    skill = RecordingSkill(meta, [])

    assert (
        not callable(getattr(skill, "__call__", None))
        or not hasattr(type(skill), "__call__")
        or type(skill).__call__ is type.__call__
    )

    with pytest.raises(TypeError):
        skill()  # type: ignore[operator]


async def test_rbac_runs_before_the_skill_body(chain):
    """A denied call must not execute anything."""
    from app.core.errors import AuthorizationError

    log: list[str] = []
    meta = SkillMeta(skill_id="SKL-OIA-01", name="research_business")
    registry = SkillRegistry(chain=chain, rbac=RBACEngine())
    registry._by_id[meta.skill_id] = RecordingSkill(meta, log)
    registry._meta[meta.skill_id] = meta

    with pytest.raises(AuthorizationError):
        await registry.execute("SKL-OIA-01", context(role=Role.VIEWER.value))

    assert log == [], "the skill body ran despite the denial"
