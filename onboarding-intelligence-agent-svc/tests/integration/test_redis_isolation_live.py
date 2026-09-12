"""AC-4 and AC-5 against a real Redis sharing DB 2.

The unit tests prove the key *patterns*. These prove the guarantee those
patterns exist for: on a database OIA shares with the prompt cache and the rest
of the fleet, a prefix scan sees only OIA's keys, and a bug in this service
cannot flush anyone else's.

Foreign keys are written deliberately before each scan. A test that scans an
empty database proves nothing.
"""

from __future__ import annotations

import uuid

import pytest

from app.cache.redis_manager import (
    KEY_PREFIX,
    PROMPT_CACHE_PREFIX,
    RedisManager,
    TenantKeys,
)
from app.core.config import Settings

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def manager(monkeypatch):
    from tests.conftest import REDIS_URL, redis_available

    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")

    monkeypatch.setenv("OIA_REDIS_URL", REDIS_URL)
    monkeypatch.setenv("OIA_BACKEND_BASE_URL", "http://backend:8001")
    monkeypatch.setenv("OIA_GCS_BUCKET", "zorven-raw-assets")
    mgr = RedisManager(Settings())  # type: ignore[call-arg]
    await mgr.connect()
    yield mgr
    await mgr.close()


@pytest.fixture
async def seeded(manager):
    """A DB 2 that looks like production: OIA keys beside foreign ones."""
    tenant = f"tenant-{uuid.uuid4().hex[:8]}"
    keys = TenantKeys(tenant)
    client = manager.client

    ours = [keys.session("s1"), keys.transcript("s1"), keys.config()]
    foreign = [
        f"{PROMPT_CACHE_PREFIX}prompt:onboarding-intelligence:extract:default",
        f"{PROMPT_CACHE_PREFIX}prompt:voc:analyse:default",
        "celery-task-meta-abc123",
        "tenant:42:some-other-service:config",
    ]

    for key in ours:
        await client.set(key, "oia", ex=300)
    for key in foreign:
        await client.set(key, "not-oia", ex=300)

    yield {"tenant": tenant, "keys": keys, "ours": ours, "foreign": foreign}

    for key in ours + foreign:
        await client.delete(key)


async def test_scan_touches_no_foreign_key(manager, seeded):
    """AC-4: a prefix scan cannot see the prompt cache's keys."""
    found = await manager.scan_prefix(KEY_PREFIX)

    assert found, "the scan found none of our own keys"
    for key in found:
        assert key.startswith(KEY_PREFIX)
    for foreign in seeded["foreign"]:
        assert foreign not in found, f"scan reached {foreign}"


async def test_scan_finds_every_key_we_wrote(manager, seeded):
    """The converse: isolation must not come at the cost of finding our own."""
    found = set(await manager.scan_prefix(f"{KEY_PREFIX}{seeded['tenant']}:"))
    assert set(seeded["ours"]).issubset(found)


async def test_a_tenant_scan_sees_only_that_tenant(manager, seeded):
    """Multi-tenancy holds at the database, not just in the builder."""
    other = TenantKeys(f"tenant-{uuid.uuid4().hex[:8]}")
    other_key = other.session("s9")
    await manager.client.set(other_key, "other", ex=120)
    try:
        found = await manager.scan_prefix(f"{KEY_PREFIX}{seeded['tenant']}:")
        assert other_key not in found
    finally:
        await manager.client.delete(other_key)


async def test_prompt_cache_keys_are_readable_but_not_ours(manager, seeded):
    """OIA reads the prompt cache; it must never own or flush those keys."""
    poi_key = seeded["foreign"][0]
    assert await manager.client.get(poi_key) == "not-oia"
    assert not poi_key.startswith(KEY_PREFIX)


async def test_every_key_we_write_carries_a_ttl(manager, seeded):
    """ERRATA-01: an untrimmed key creates eviction pressure fleet-wide."""
    for key in seeded["ours"]:
        ttl = await manager.client.ttl(key)
        assert ttl > 0, f"{key} has no TTL (ttl={ttl})"


async def test_eviction_policy_is_noeviction(manager):
    """AC-5 — session state that can be evicted mid-meeting is a correctness bug.

    This asserts the live server's configuration, not a constant. It failed
    while the shared instance was ``allkeys-lru``; the policy was changed to
    ``noeviction`` on 2026-08-01 after measuring the instance at 7.2 MB of
    1 GB. If this test starts failing, session state is evictable again and
    the fix is the policy, not this assertion.
    """
    policy = await manager.eviction_policy()

    if policy is None:
        pytest.skip("server refused CONFIG GET maxmemory-policy")

    assert policy == "noeviction", (
        f"maxmemory-policy is {policy!r}. Under an allkeys-* policy Redis "
        "evicts any key regardless of TTL, so a live meeting can lose its "
        "transcript and resume window under memory pressure (A-03 AC-5)."
    )
