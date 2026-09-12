"""M-01 · Integration tests for guardrail infrastructure.

Requires a running Redis on localhost:6379 (skipped otherwise).
"""

from __future__ import annotations

import pytest

from app.cache.redis_manager import TenantKeys, TTL_RATELIMIT
from app.logic.guardrails import Action, GuardrailChain, Layer, Verdict
from app.logic.input_guardrails import ig07_rate_limit
from app.skills.models import SkillContext, TenantContext

pytestmark = pytest.mark.integration

TENANT = "t-integration-m01"
USER = "u-rate-test"


@pytest.fixture
def ctx() -> SkillContext:
    return SkillContext(
        input_prompt="test",
        tenant_context=TenantContext(tenant_id=TENANT, user_id=USER),
        config={},
        correlation_id="integration-test",
    )


async def test_ig07_redis_rate_counter(live_redis, ctx):
    """IG-07 pre-fetch pattern: real Redis INCR + EXPIRE, counter resets."""
    keys = TenantKeys(TENANT)
    rate_key = keys.ratelimit(USER)
    client = live_redis.client

    await client.delete(rate_key)

    count_raw = await client.get(rate_key)
    assert count_raw is None

    await client.incr(rate_key)
    await client.expire(rate_key, TTL_RATELIMIT)

    count_after = int(await client.get(rate_key))
    assert count_after == 1

    ctx.config["_ig07_count"] = count_after
    ctx.config["_rate_limit"] = 10
    v = ig07_rate_limit({}, ctx)
    assert v.action is Action.PASS

    for _ in range(9):
        await client.incr(rate_key)

    count_over = int(await client.get(rate_key))
    assert count_over == 10

    ctx.config["_ig07_count"] = count_over
    v = ig07_rate_limit({}, ctx)
    assert v.action is Action.BLOCK

    await client.delete(rate_key)


async def test_evt004_collected_on_triggered_rule(ctx):
    """AC-4: non-PASS verdicts collected for EVT-004 emission."""

    def escalating_rule(payload, context):
        return Verdict(
            rule_id="IG-03",
            action=Action.ESCALATE,
            detail="test escalation",
            payload=payload,
        )

    chain = GuardrailChain(ig_budget_ms=10000)
    chain.register(Layer.INPUT, "IG-03", escalating_rule)

    chain.evaluate(Layer.INPUT, {"text": "test"}, ctx)

    triggered = chain.drain_triggered()
    assert len(triggered) == 1
    item = triggered[0]
    assert item["rule_id"] == "IG-03"
    assert item["action"] == "ESCALATE"
    assert item["tenant_id"] == TENANT
    assert item["layer"] == "IG"
    assert "elapsed_ms" in item
