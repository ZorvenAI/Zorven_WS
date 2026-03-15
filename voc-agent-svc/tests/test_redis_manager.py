"""Tests for the RedisManager."""

import pytest

from app.cache.redis_manager import RedisManager


@pytest.mark.unit
def test_cache_key_deterministic():
    """Same inputs produce the same cache key."""
    key1 = RedisManager._cache_key("prompt", {"k": "v"}, "t1")
    key2 = RedisManager._cache_key("prompt", {"k": "v"}, "t1")
    assert key1 == key2


@pytest.mark.unit
def test_cache_key_includes_tenant():
    """Cache key contains the tenant_id prefix."""
    key = RedisManager._cache_key("prompt", {}, "my-tenant")
    assert "voca:my-tenant:result:" in key


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_rate_limit_no_redis():
    """Fail-open: check_rate_limit returns True when Redis is unavailable."""
    mgr = RedisManager()
    # _redis is None by default (no connect() called)
    result = await mgr.check_rate_limit("tenant-1")
    assert result is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_check_idempotency_no_redis():
    """Fail-open: check_idempotency returns True when Redis is unavailable."""
    mgr = RedisManager()
    result = await mgr.check_idempotency("some-key")
    assert result is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_cached_result_no_redis():
    """Fail-open: get_cached_result returns None when Redis is unavailable."""
    mgr = RedisManager()
    result = await mgr.get_cached_result("prompt", {}, "t1")
    assert result is None
