"""C-02 · the PREP executor and the research-brief cache (AC-2).

Real Redis throughout — the cache is the feature under test, and a fake one
would prove only that the code calls the methods the author expected.
"""

from __future__ import annotations

import uuid

import pytest

from app.cache.redis_manager import TTL_BRIEF, RedisManager
from app.core.config import get_settings
from app.logic.grounding import RULE_ID as OG_01
from app.logic.guardrails import Layer
from app.logic.prep_executor import RESEARCH_SKILL, PrepExecutor
from app.skills.models import TenantContext

pytestmark = pytest.mark.integration


def unique(prefix: str) -> str:
    """Real Redis outlives the process; fixed ids made C-01's tests pass once
    and never again."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture
async def redis():
    manager = RedisManager(get_settings())
    await manager.connect()
    try:
        yield manager
    finally:
        await manager.close()


@pytest.fixture
def executor(redis):
    """No providers wired, so the skill degrades — which is the right default
    for these tests: they are about caching and dispatch, not research."""
    return PrepExecutor(redis)


def tenant(tenant_id: str) -> TenantContext:
    return TenantContext(tenant_id=tenant_id, user_id="u-1", role="ADMIN")


# ── Dispatch ─────────────────────────────────────────────────────────


async def test_the_executor_runs_the_research_skill(executor):
    brief, from_cache = await executor.research(
        tenant=tenant(unique("t")),
        input_context={"company_name": unique("Acme")},
        input_prompt="prep",
    )

    assert from_cache is False
    assert "open_unknowns" in brief
    assert brief["degraded"] is True, "no providers were wired"


async def test_the_real_og_01_is_installed_on_the_chain(executor):
    """Not the A-06 no-op. If the registration were missed, grounding would
    silently stop applying and every test of it would still pass in isolation.
    """
    chain = executor.registry.chain
    assert OG_01 in chain.rules(Layer.OUTPUT)

    from app.logic.grounding import ground_output

    installed = [r for r in chain._rules[Layer.OUTPUT] if r.rule_id == OG_01][0]
    assert installed.evaluate is ground_output


async def test_the_research_skill_resolves(executor):
    assert executor.registry.get(RESEARCH_SKILL) is not None


# ── AC-2 · the brief survives the turn ───────────────────────────────


async def test_a_brief_is_available_without_re_running_research(redis, executor):
    """AC-2: "the same brief is available without re-running research"."""
    tid, company = unique("t"), unique("Kalyani")
    stored = {"company_name": company, "facts": [], "degraded": False}

    await executor.store_brief(tid, company, stored)
    got = await executor.cached_brief(tid, company)

    assert got == stored


async def test_the_second_turn_reads_the_cache(redis, executor):
    tid, company = unique("t"), unique("Kalyani")
    await executor.store_brief(
        tid, company, {"company_name": company, "degraded": False}
    )

    _, from_cache = await executor.research(
        tenant=tenant(tid),
        input_context={"company_name": company},
        input_prompt="again",
    )

    assert from_cache is True


async def test_the_cache_key_normalises_the_company_name(redis, executor):
    """The whole point of normalising: an operator retyping the name should
    not pay for a fresh round of paid search."""
    tid = unique("t")
    slug = uuid.uuid4().hex[:8]
    await executor.store_brief(tid, f"Kalyani {slug}", {"degraded": False, "n": 1})

    got = await executor.cached_brief(tid, f"  kalyani   {slug} Pvt. Ltd.  ")

    assert got == {"degraded": False, "n": 1}


async def test_briefs_do_not_bleed_between_tenants(redis, executor):
    company = unique("Shared")
    await executor.store_brief(unique("t"), company, {"degraded": False, "secret": 1})

    assert await executor.cached_brief(unique("t"), company) is None


async def test_the_brief_key_carries_a_ttl(redis, executor):
    """DB 2 is shared with ten other services (ERRATA-01); an untimed key is a
    slow leak that evicts someone else's data."""
    tid, company = unique("t"), unique("Kalyani")
    await executor.store_brief(tid, company, {"degraded": False})

    ttl = await redis.client.ttl(executor._brief_key(tid, company))

    assert 0 < ttl <= TTL_BRIEF


async def test_a_degraded_brief_is_never_cached(redis, executor):
    """A degraded brief is the *absence* of research. Caching it would let a
    one-minute Tavily outage suppress real research for the next hour, with
    nothing to tell the operator why their questions stayed thin.
    """
    tid, company = unique("t"), unique("Kalyani")

    await executor.store_brief(tid, company, {"degraded": True, "degraded_reason": "x"})

    assert await executor.cached_brief(tid, company) is None


async def test_a_degraded_research_run_leaves_the_cache_empty(redis, executor):
    """The same property through the real path rather than the setter."""
    tid, company = unique("t"), unique("Kalyani")

    brief, _ = await executor.research(
        tenant=tenant(tid),
        input_context={"company_name": company},
        input_prompt="prep",
    )

    assert brief["degraded"] is True
    assert await executor.cached_brief(tid, company) is None


async def test_a_corrupt_cache_entry_costs_a_rerun_not_the_turn(redis, executor):
    tid, company = unique("t"), unique("Kalyani")
    await redis.client.set(executor._brief_key(tid, company), "{not json")

    assert await executor.cached_brief(tid, company) is None


async def test_the_cache_can_be_bypassed(redis, executor):
    """C-04 lets an operator ask for a re-run; the seam has to exist."""
    tid, company = unique("t"), unique("Kalyani")
    await executor.store_brief(tid, company, {"degraded": False})

    _, from_cache = await executor.research(
        tenant=tenant(tid),
        input_context={"company_name": company},
        input_prompt="again",
        use_cache=False,
    )

    assert from_cache is False
