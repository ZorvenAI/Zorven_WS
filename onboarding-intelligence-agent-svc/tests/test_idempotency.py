"""B-06 (Gap 5) — IdempotencyGuard unit tests.

No mocks: real Redis for every assertion.
"""

from __future__ import annotations

import pytest

from app.cache.idempotency import IdempotencyGuard
from app.cache.redis_manager import RedisManager, TTL_IDEMPOTENCY

pytestmark = pytest.mark.integration


@pytest.fixture
def guard(live_redis: RedisManager) -> IdempotencyGuard:
    return IdempotencyGuard(live_redis)


TENANT = "t-idem-test"


async def test_check_returns_none_when_key_missing(guard: IdempotencyGuard):
    result = await guard.check(TENANT, "nonexistent-digest")
    assert result is None


async def test_store_then_check_returns_stored_payload(guard: IdempotencyGuard):
    payload = {"job_id": "j1", "status": "ACCEPTED"}
    await guard.store(TENANT, "digest-abc", payload)
    cached = await guard.check(TENANT, "digest-abc")
    assert cached == payload


async def test_check_returns_none_on_corrupt_json(
    guard: IdempotencyGuard, live_redis: RedisManager
):
    keys = live_redis.keys_for(TENANT)
    key = keys.idempotency("corrupt-key")
    await live_redis.client.set(key, b"not-json{{{", ex=60)

    result = await guard.check(TENANT, "corrupt-key")
    assert result is None


async def test_store_uses_custom_ttl(guard: IdempotencyGuard, live_redis: RedisManager):
    await guard.store(TENANT, "short-ttl", {"x": 1}, ttl=10)
    keys = live_redis.keys_for(TENANT)
    key = keys.idempotency("short-ttl")
    ttl = await live_redis.client.ttl(key)
    assert 1 <= ttl <= 10


async def test_store_default_ttl_is_24h(
    guard: IdempotencyGuard, live_redis: RedisManager
):
    await guard.store(TENANT, "default-ttl", {"x": 1})
    keys = live_redis.keys_for(TENANT)
    key = keys.idempotency("default-ttl")
    ttl = await live_redis.client.ttl(key)
    assert TTL_IDEMPOTENCY - 5 <= ttl <= TTL_IDEMPOTENCY


async def test_different_tenants_are_isolated(guard: IdempotencyGuard):
    await guard.store("tenant-a", "same-digest", {"from": "a"})
    await guard.store("tenant-b", "same-digest", {"from": "b"})

    a = await guard.check("tenant-a", "same-digest")
    b = await guard.check("tenant-b", "same-digest")
    assert a == {"from": "a"}
    assert b == {"from": "b"}


async def test_different_digests_are_isolated(guard: IdempotencyGuard):
    await guard.store(TENANT, "d1", {"v": 1})
    await guard.store(TENANT, "d2", {"v": 2})

    assert (await guard.check(TENANT, "d1")) == {"v": 1}
    assert (await guard.check(TENANT, "d2")) == {"v": 2}


async def test_store_overwrites_existing(guard: IdempotencyGuard):
    await guard.store(TENANT, "overwrite", {"v": 1})
    await guard.store(TENANT, "overwrite", {"v": 2})
    assert (await guard.check(TENANT, "overwrite")) == {"v": 2}


async def test_check_returns_none_for_non_dict_json(
    guard: IdempotencyGuard, live_redis: RedisManager
):
    """Valid JSON that is not a dict (list, string, number) is a miss."""
    keys = live_redis.keys_for(TENANT)
    for label, value in [("list", "[1,2,3]"), ("str", '"hello"'), ("num", "42")]:
        key = keys.idempotency(f"non-dict-{label}")
        await live_redis.client.set(key, value, ex=60)
        assert await guard.check(TENANT, f"non-dict-{label}") is None
