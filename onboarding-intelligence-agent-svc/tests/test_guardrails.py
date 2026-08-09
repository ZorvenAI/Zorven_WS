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


def test_registering_a_rule_replaces_it_in_place(chain):
    """M-01 fills bodies in through this door **without changing the order**.

    §5 numbers its rules in the order an operator reads them, and the order is
    load-bearing: IG-04 redacts, IG-06 truncates, and truncating before
    redacting would cut text that had not been redacted yet.
    """
    before = chain.rules(Layer.INPUT)

    def rule(payload, ctx):
        return Verdict(rule_id="IG-01")

    chain.register(Layer.INPUT, "IG-01", rule)

    assert chain.rules(Layer.INPUT) == before, "replacement reordered the layer"


def test_registering_a_new_rule_appends_it(chain):
    """A rule §5 does not declare is appended rather than silently dropped."""
    before = chain.rules(Layer.OUTPUT)
    chain.register(Layer.OUTPUT, "OG-99", lambda p, c: Verdict(rule_id="OG-99"))
    assert chain.rules(Layer.OUTPUT) == before + ["OG-99"]


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


# ── Regression cover for PR #533 review findings ──────────────────────────


async def test_input_transforms_reach_the_skill_body(chain):
    """Review finding: execute() discarded the evaluated payload.

    IG-04 redacts and IG-06 truncates. A transform the skill never sees is
    not a guardrail, it is a log line.
    """
    seen: dict = {}

    class Capturing(BaseSkill):
        async def run(self, ctx: SkillContext) -> SkillResult:
            seen.update(ctx.input_context)
            return SkillResult(skill_id=self.meta.skill_id, output={"ok": True})

    def redactor(payload, ctx):
        return Verdict(
            rule_id="IG-04",
            action=Action.REDACT,
            payload={**payload, "secret": "***"},
        )

    chain.register(Layer.INPUT, "IG-04", redactor)

    meta = SkillMeta(skill_id="SKL-OIA-01", name="research_business")
    registry = SkillRegistry(chain=chain, rbac=RBACEngine())
    registry._by_id[meta.skill_id] = Capturing(meta)
    registry._meta[meta.skill_id] = meta

    ctx = context()
    ctx.input_context["secret"] = "hunter2"
    await registry.execute("SKL-OIA-01", ctx)

    assert seen["secret"] == "***", "the skill saw the un-redacted input"
    assert ctx.input_context["secret"] == "***"


async def test_output_transforms_reach_the_caller(chain):
    """Review finding: evaluate_result() discarded the transformed output.

    OG-02 re-applies redaction on egress; discarding it would hand the caller
    exactly the output that rule just rewrote.
    """

    class Emitting(BaseSkill):
        async def run(self, ctx: SkillContext) -> SkillResult:
            return SkillResult(skill_id=self.meta.skill_id, output={"email": "a@b.c"})

    def scrubber(payload, ctx):
        return Verdict(
            rule_id="OG-02", action=Action.REDACT, payload={**payload, "email": "***"}
        )

    chain.register(Layer.OUTPUT, "OG-02", scrubber)

    meta = SkillMeta(skill_id="SKL-OIA-01", name="research_business")
    registry = SkillRegistry(chain=chain, rbac=RBACEngine())
    registry._by_id[meta.skill_id] = Emitting(meta)
    registry._meta[meta.skill_id] = meta

    result = await registry.execute("SKL-OIA-01", context())
    assert result.output["email"] == "***", "the caller got the pre-guardrail output"


# ── OG-01, with a real body (C-02) ───────────────────────────────────


def _research_context():
    from app.skills.models import SkillContext, TenantContext

    return SkillContext(
        input_prompt="prep",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context={},
    )


def test_og_unsourced_fact_moves_to_unknowns():
    """The C-02 card's named case: "OG grounding applies to research too".

    Demotion, not deletion. A claim the agent could not source is a thing
    worth *asking about*, and SKL-OIA-02 turns unknowns straight into
    questions — deleting it would throw away the signal that the agent looked
    and came back empty.
    """
    from app.logic.grounding import ground_output

    verdict = ground_output(
        {
            "facts": [
                {"statement": "Founded 2016.", "source_url": "https://x.example/a"},
                {"statement": "Revenue is 40 crore.", "source_url": ""},
            ],
            "open_unknowns": ["What is their AOV?"],
        },
        _research_context(),
    )

    assert verdict.action is Action.DROP
    assert verdict.payload["facts"] == [
        {"statement": "Founded 2016.", "source_url": "https://x.example/a"}
    ]
    assert verdict.payload["open_unknowns"] == [
        "What is their AOV?",
        "Unverified: Revenue is 40 crore.",
    ]


def test_og_01_passes_a_fully_sourced_payload_through_unchanged():
    from app.logic.grounding import ground_output

    payload = {
        "facts": [{"statement": "Founded 2016.", "source_url": "https://x.example/a"}],
        "open_unknowns": [],
    }

    verdict = ground_output(payload, _research_context())

    assert verdict.action is Action.PASS
    assert verdict.payload == payload


def test_og_01_does_not_ground_the_unknowns_list():
    """An unknown is by definition unsourced. A universal rule would strip the
    most valuable part of the brief."""
    from app.logic.grounding import ground_output

    verdict = ground_output(
        {"facts": [], "open_unknowns": ["no source, and that is the point"]},
        _research_context(),
    )

    assert verdict.action is Action.PASS
    assert verdict.payload["open_unknowns"] == ["no source, and that is the point"]


@pytest.mark.parametrize(
    "bad_url", ["", "   ", "unknown", "the company website", "ftp://x", None, 42]
)
def test_og_01_rejects_anything_that_is_not_an_http_url(bad_url):
    """ "the company website" is not a citation. The rule exists to stop a
    plausible-looking string standing in for one."""
    from app.logic.grounding import ground_output

    verdict = ground_output(
        {"facts": [{"statement": "A claim.", "source_url": bad_url}]},
        _research_context(),
    )

    assert verdict.payload["facts"] == []
    assert verdict.payload["open_unknowns"] == ["Unverified: A claim."]


def test_og_01_is_registered_in_place_not_appended():
    """A-06's ordering guarantee. §5 numbers its rules in reading order, and a
    replacement that moved OG-01 to the end would let later rules act on
    ungrounded values first.
    """
    from app.logic.grounding import RULE_ID, ground_output

    chain = GuardrailChain()
    before = chain.rules(Layer.OUTPUT)

    chain.register(Layer.OUTPUT, RULE_ID, ground_output)

    assert chain.rules(Layer.OUTPUT) == before
    assert chain.rules(Layer.OUTPUT)[0] == "OG-01"
