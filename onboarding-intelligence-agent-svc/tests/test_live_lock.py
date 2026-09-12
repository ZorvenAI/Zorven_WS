"""M-05 AC-2/AC-3 — live-session lock: company keying, multi-slot, TTL expiry.

Tests hit a real Redis: no mocks. The lock key is
``oia:v1:{tenant}:lock:live:{company_id}`` with a 90s TTL refreshed every 30s
by the heartbeat.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid

import pytest

from app.logic.live_lock import LOCK_TTL_S, LiveLock, acquire

pytestmark = pytest.mark.integration

TENANT = "t-lock-test"


def _company(suffix: str) -> str:
    return f"c-{hashlib.md5(suffix.encode()).hexdigest()[:8]}"


async def _cleanup(redis_manager, tenant_id: str, company_id: str, slots: int = 5):
    keys = redis_manager.keys_for(tenant_id)
    for slot in range(slots):
        key = keys.live_lock_slot(company_id, slot)
        await redis_manager.client.delete(key)


async def test_live_lock_keyed_on_company(live_redis):
    """AC-2: two different companies can lock simultaneously; same company
    contends."""
    company_a = _company("lock-a")
    company_b = _company("lock-b")
    token_a = uuid.uuid4().hex
    token_b = uuid.uuid4().hex

    try:
        lock_a = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company_a,
            token=token_a,
        )
        lock_b = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company_b,
            token=token_b,
        )
        assert lock_a is not None
        assert lock_b is not None

        contender = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company_a,
            token=uuid.uuid4().hex,
        )
        assert contender is None
    finally:
        await _cleanup(live_redis, TENANT, company_a)
        await _cleanup(live_redis, TENANT, company_b)


async def test_tenant_configurable_max_concurrent(live_redis):
    """AC-2: max_concurrent=2 allows two sessions for one company."""
    company = _company("multi-slot")
    try:
        lock1 = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company,
            token=uuid.uuid4().hex,
            max_slots=2,
        )
        lock2 = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company,
            token=uuid.uuid4().hex,
            max_slots=2,
        )
        assert lock1 is not None
        assert lock2 is not None
        assert lock1.key != lock2.key

        lock3 = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company,
            token=uuid.uuid4().hex,
            max_slots=2,
        )
        assert lock3 is None
    finally:
        await _cleanup(live_redis, TENANT, company)


async def test_slot_zero_backward_compatible(live_redis):
    """Slot 0 produces the same key as live_lock() for backward compatibility."""
    company = _company("compat")
    keys = live_redis.keys_for(TENANT)
    assert keys.live_lock_slot(company, 0) == keys.live_lock(company)


async def test_lock_ttl_releases_after_crash(live_redis):
    """AC-3: a crashed lock cannot strand a company. After TTL expires, a new
    acquire succeeds.

    Uses a short TTL via direct SET to avoid waiting 90 seconds.
    """
    company = _company("crash")
    keys = live_redis.keys_for(TENANT)
    key = keys.live_lock(company)
    client = live_redis.client

    try:
        await client.set(key, "crashed-token", nx=True, ex=2)

        contender = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company,
            token=uuid.uuid4().hex,
        )
        assert contender is None

        await asyncio.sleep(2.2)

        recovered = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company,
            token=uuid.uuid4().hex,
        )
        assert recovered is not None
    finally:
        await _cleanup(live_redis, TENANT, company)


async def test_lock_refresh_extends_ttl(live_redis):
    """AC-3: refresh resets TTL so the lock outlives the initial expiry."""
    company = _company("refresh")
    client = live_redis.client

    try:
        lock = await acquire(
            live_redis,
            tenant_id=TENANT,
            company_id=company,
            token=uuid.uuid4().hex,
        )
        assert lock is not None

        ttl_before = await client.ttl(lock.key)
        assert 0 < ttl_before <= LOCK_TTL_S

        refreshed = await lock.refresh()
        assert refreshed is True

        ttl_after = await client.ttl(lock.key)
        assert ttl_after > 0
    finally:
        await _cleanup(live_redis, TENANT, company)


async def test_release_only_deletes_own_token(live_redis):
    """A lock that expired and was re-acquired by another socket must not be
    released by the original holder."""
    company = _company("token-check")
    keys = live_redis.keys_for(TENANT)
    key = keys.live_lock(company)
    client = live_redis.client

    try:
        stale_lock = LiveLock(key=key, token="old-token", _client=client)
        await client.set(key, "new-owner", ex=LOCK_TTL_S)

        await stale_lock.release()

        value = await client.get(key)
        assert value == "new-owner"
    finally:
        await _cleanup(live_redis, TENANT, company)


async def test_acquire_returns_none_without_redis():
    """No Redis manager → None, not an exception."""
    lock = await acquire(
        None,
        tenant_id=TENANT,
        company_id="c-1",
        token="tok",
    )
    assert lock is None


async def test_acquire_returns_none_without_company(live_redis):
    """Empty company id → None, not an exception."""
    lock = await acquire(
        live_redis,
        tenant_id=TENANT,
        company_id="",
        token="tok",
    )
    assert lock is None
