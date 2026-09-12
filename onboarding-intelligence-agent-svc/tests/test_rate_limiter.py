"""M-05 AC-1 — per-user rate limiting via Redis counters.

Tests hit a real Redis: no mocks. The counter lives at
``oia:v1:{tenant}:ratelimit:{user_id}`` with a 60-second TTL on the first
increment, shared by PREP turns and WS control frames.
"""

from __future__ import annotations

import asyncio

import pytest

from app.logic.rate_limiter import WINDOW_S, check_rate

pytestmark = pytest.mark.integration

TENANT = "t-rl-test"
USER = "u-rl-1"


@pytest.fixture
def rl_key(live_redis):
    """A ratelimit key scoped to this test run, cleaned up afterward."""
    keys = live_redis.keys_for(TENANT)
    key = keys.ratelimit(USER)
    yield key
    asyncio.get_event_loop().run_until_complete(live_redis.client.delete(key))


async def test_rate_limit_increments_and_expires(live_redis, rl_key):
    """AC-1: counter increments on each call, and the 60s TTL is set."""
    client = live_redis.client

    count1, exceeded1 = await check_rate(client, rl_key, 10)
    assert count1 == 1
    assert exceeded1 is False

    ttl = await client.ttl(rl_key)
    assert 0 < ttl <= WINDOW_S

    count2, exceeded2 = await check_rate(client, rl_key, 10)
    assert count2 == 2
    assert exceeded2 is False


async def test_rate_limit_blocks_after_threshold(live_redis, rl_key):
    """AC-1: returns exceeded=True when count > limit."""
    client = live_redis.client
    limit = 3

    for i in range(1, limit + 1):
        count, exceeded = await check_rate(client, rl_key, limit)
        assert count == i
        assert exceeded is False

    count, exceeded = await check_rate(client, rl_key, limit)
    assert count == limit + 1
    assert exceeded is True


async def test_rate_limit_ttl_not_reset_on_subsequent_calls(live_redis, rl_key):
    """The TTL is set once, on the first increment — not refreshed."""
    client = live_redis.client

    await check_rate(client, rl_key, 10)
    ttl_after_first = await client.ttl(rl_key)

    await asyncio.sleep(1.1)
    await check_rate(client, rl_key, 10)
    ttl_after_second = await client.ttl(rl_key)

    assert ttl_after_second < ttl_after_first


def test_prep_returns_429_when_rate_exceeded(app_with_live_redis):
    """AC-1: ``/v1/execute`` returns HTTP 429 when the rate limit is hit."""
    import redis as sync_redis

    from app.cache.redis_manager import TenantKeys
    from tests.conftest import REDIS_URL

    from fastapi.testclient import TestClient

    tenant_id = "t-429-test"
    user_id = "u-429"

    rl_key = TenantKeys(tenant_id).ratelimit(user_id)

    r = sync_redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.delete(rl_key)
        r.set(rl_key, "10", ex=60)
    finally:
        r.close()

    with TestClient(app_with_live_redis) as client:
        settings = app_with_live_redis.state.settings
        body = {
            "input_prompt": "Tell me about the brand",
            "chat_session_id": "chat-429",
            "tenant_context": {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role": "EDITOR",
                "trace_id": "tr-429",
            },
        }
        headers = {"X-Service-Token": settings.SERVICE_TOKEN}

        response = client.post("/v1/execute", json=body, headers=headers)
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]

    r = sync_redis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.delete(rl_key)
    finally:
        r.close()
