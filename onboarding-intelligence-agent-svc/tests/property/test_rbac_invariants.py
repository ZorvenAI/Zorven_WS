"""Property tests for the RBAC evaluator and the guardrail chain.

The example-based suites check the rows §15 argues for. These check that the
evaluator is *total* and the chain's ordering holds under inputs nobody
enumerated — arbitrary registration orders, arbitrary yield counts.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.guardrails import (
    OUTPUT_RULES,
    Action,
    GuardrailChain,
    Layer,
    Verdict as RuleVerdict,
)
from app.rbac.engine import Capability, RBACEngine, Role, Verdict
from app.skills.models import SkillContext, TenantContext

pytestmark = pytest.mark.property

roles = st.sampled_from(list(Role))
capabilities = st.sampled_from(list(Capability))
skill_ids = st.sampled_from([f"SKL-OIA-{n:02d}" for n in range(1, 17)])


def context() -> SkillContext:
    return SkillContext(
        input_prompt="p",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )


@given(role=roles, capability=capabilities)
def test_evaluator_is_total(role, capability):
    """Every pair returns exactly one known verdict and never raises."""
    assert RBACEngine().verdict(role, capability) in set(Verdict)


@given(role=roles, skill_id=skill_ids)
def test_every_declared_skill_is_decided(role, skill_id):
    assert RBACEngine().verdict_for_skill(role, skill_id) in set(Verdict)


@given(role=roles, skill_id=skill_ids)
def test_enforce_raises_exactly_when_the_verdict_is_deny(role, skill_id):
    from app.core.errors import AuthorizationError

    engine = RBACEngine()
    verdict = engine.verdict_for_skill(role, skill_id)
    if verdict is Verdict.DENY:
        with pytest.raises(AuthorizationError):
            engine.enforce(role, skill_id)
    else:
        assert engine.enforce(role, skill_id) is verdict


@given(role=roles, skill_id=st.text(min_size=1, max_size=20))
def test_an_unknown_skill_is_never_allowed(role, skill_id):
    """A typo in a skill id must not become an accidental grant."""
    engine = RBACEngine()
    if skill_id in [f"SKL-OIA-{n:02d}" for n in range(1, 17)]:
        return
    assert engine.verdict_for_skill(role, skill_id) is Verdict.DENY


@given(order=st.permutations(["OG-01", "OG-02", "OG-03"]))
def test_registration_order_does_not_change_layer_membership(order):
    """Rules may be registered in any order; the layer still holds all of them."""
    chain = GuardrailChain()
    for rule_id in order:
        chain.register(
            Layer.OUTPUT, rule_id, lambda p, c, r=rule_id: RuleVerdict(rule_id=r)
        )
    assert set(chain.rules(Layer.OUTPUT)) == set(OUTPUT_RULES)
    assert len(chain.rules(Layer.OUTPUT)) == len(OUTPUT_RULES)


@given(chunks=st.integers(min_value=0, max_value=20))
@settings(max_examples=30)
def test_output_guardrails_run_once_per_chunk(chunks):
    """For any yield count, OG evaluates exactly that many times."""
    import asyncio

    async def produce():
        for index in range(chunks):
            yield {"seq": index}

    async def drain():
        chain = GuardrailChain()
        seen = [c async for c in chain.wrap_stream(produce(), context())]
        og = [c for c in chain.calls if c[0] is Layer.OUTPUT]
        assert len(seen) == chunks
        assert len(og) == chunks * len(OUTPUT_RULES)

    asyncio.run(drain())


@given(blocking_index=st.integers(min_value=0, max_value=5))
def test_a_block_anywhere_stops_the_layer(blocking_index):
    """Whichever rule blocks, nothing after it runs."""
    from app.logic.guardrails import GuardrailViolation

    chain = GuardrailChain()
    rule_ids = chain.rules(Layer.OUTPUT)
    target = rule_ids[blocking_index % len(rule_ids)]
    chain.register(
        Layer.OUTPUT,
        target,
        lambda p, c: RuleVerdict(rule_id=target, action=Action.BLOCK),
    )

    with pytest.raises(GuardrailViolation) as exc:
        chain.evaluate(Layer.OUTPUT, {"x": 1}, context())
    assert exc.value.verdict.rule_id == target
