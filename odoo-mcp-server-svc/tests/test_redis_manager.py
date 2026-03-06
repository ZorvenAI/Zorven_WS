"""Tests for app/cache/redis_manager.py — full coverage.

Mocks redis.asyncio to avoid real Redis connections.
"""

import hashlib
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.redis_manager import RedisManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_redis() -> AsyncMock:
    """Return an AsyncMock that behaves like an aioredis.Redis client."""
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    r.aclose = AsyncMock()
    return r


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_url(self):
        mgr = RedisManager("redis://localhost:6379/9")
        assert mgr.redis_url == "redis://localhost:6379/9"
        assert mgr._redis is None


# ---------------------------------------------------------------------------
# _get_redis — lazy initialization
# ---------------------------------------------------------------------------


class TestGetRedis:
    @patch("app.cache.redis_manager.aioredis")
    async def test_creates_client_on_first_call(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://localhost:6379/9")
        result = await mgr._get_redis()

        mock_aioredis.from_url.assert_called_once_with(
            "redis://localhost:6379/9", decode_responses=True
        )
        assert result is mock_client

    @patch("app.cache.redis_manager.aioredis")
    async def test_returns_same_instance_on_second_call(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://localhost:6379/9")
        first = await mgr._get_redis()
        second = await mgr._get_redis()

        assert first is second
        assert mock_aioredis.from_url.call_count == 1


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    async def test_close_when_redis_exists(self):
        mock_client = _make_mock_redis()
        mgr = RedisManager("redis://test")
        mgr._redis = mock_client

        await mgr.close()

        mock_client.aclose.assert_awaited_once()
        assert mgr._redis is None

    async def test_close_when_redis_is_none(self):
        mgr = RedisManager("redis://test")
        assert mgr._redis is None
        await mgr.close()  # should not raise
        assert mgr._redis is None


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    @patch("app.cache.redis_manager.aioredis")
    async def test_within_limit(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.incr.return_value = 5
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.check_rate_limit("tenant-1", limit=10)

        assert result is True
        mock_client.incr.assert_awaited_once_with("odoo_mcp:rate:tenant-1")

    @patch("app.cache.redis_manager.aioredis")
    async def test_exceeds_limit(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.incr.return_value = 11
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.check_rate_limit("tenant-1", limit=10)

        assert result is False

    @patch("app.cache.redis_manager.aioredis")
    async def test_first_increment_sets_expire(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.incr.return_value = 1
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.check_rate_limit("k", limit=100)

        mock_client.expire.assert_awaited_once_with("odoo_mcp:rate:k", 60)

    @patch("app.cache.redis_manager.aioredis")
    async def test_subsequent_increment_skips_expire(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.incr.return_value = 2
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.check_rate_limit("k", limit=100)

        mock_client.expire.assert_not_awaited()

    @patch("app.cache.redis_manager.aioredis")
    async def test_uses_default_limit_when_none(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.incr.return_value = 1
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.check_rate_limit("k")

        # Default RATE_LIMIT_PER_MINUTE is 60; count=1 <= 60 => True
        assert result is True

    @patch("app.cache.redis_manager.aioredis")
    async def test_fail_open_on_exception(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.incr.side_effect = ConnectionError("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.check_rate_limit("k", limit=10)

        assert result is True  # fail-open


# ---------------------------------------------------------------------------
# get_schema / set_schema
# ---------------------------------------------------------------------------


class TestSchemaCache:
    @patch("app.cache.redis_manager.aioredis")
    async def test_get_schema_hit(self, mock_aioredis):
        schema = {"fields": ["name", "id"]}
        mock_client = _make_mock_redis()
        mock_client.get.return_value = json.dumps(schema)
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_schema("t1", "res.partner")

        assert result == schema
        mock_client.get.assert_awaited_once_with("odoo_mcp:schema:t1:res.partner")

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_schema_miss(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_schema("t1", "res.partner")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_schema_fail_open(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.side_effect = ConnectionError("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_schema("t1", "res.partner")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_schema_happy(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        schema = {"fields": ["name"]}
        await mgr.set_schema("t1", "res.partner", schema)

        mock_client.set.assert_awaited_once()
        args, kwargs = mock_client.set.call_args
        assert args[0] == "odoo_mcp:schema:t1:res.partner"
        assert json.loads(args[1]) == schema

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_schema_fail_silently(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = ConnectionError("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_schema("t1", "res.partner", {"x": 1})
        # Should not raise


# ---------------------------------------------------------------------------
# get_session / set_session
# ---------------------------------------------------------------------------


class TestSessionCache:
    @patch("app.cache.redis_manager.aioredis")
    async def test_get_session_hit(self, mock_aioredis):
        session = {"uid": 2, "db": "prod"}
        mock_client = _make_mock_redis()
        mock_client.get.return_value = json.dumps(session)
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_session("t1")

        assert result == session
        mock_client.get.assert_awaited_once_with("odoo_mcp:session:t1")

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_session_miss(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_session("t1")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_session_fail_open(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.side_effect = Exception("boom")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_session("t1")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_session_happy(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_session("t1", {"uid": 2})

        mock_client.set.assert_awaited_once()
        args, kwargs = mock_client.set.call_args
        assert args[0] == "odoo_mcp:session:t1"

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_session_fail_silently(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = Exception("boom")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_session("t1", {"uid": 2})
        # Should not raise


# ---------------------------------------------------------------------------
# get_rbac / set_rbac
# ---------------------------------------------------------------------------


class TestRBACCache:
    @patch("app.cache.redis_manager.aioredis")
    async def test_get_rbac_hit(self, mock_aioredis):
        policy = {"allowed_models": ["res.partner"]}
        mock_client = _make_mock_redis()
        mock_client.get.return_value = json.dumps(policy)
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_rbac("t1", "admin")

        assert result == policy
        mock_client.get.assert_awaited_once_with("odoo_mcp:rbac:t1:admin")

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_rbac_miss(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_rbac("t1", "admin")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_rbac_fail_open(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.side_effect = Exception("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_rbac("t1", "admin")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_rbac_happy(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_rbac("t1", "admin", {"allowed": True})

        mock_client.set.assert_awaited_once()
        args, kwargs = mock_client.set.call_args
        assert args[0] == "odoo_mcp:rbac:t1:admin"

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_rbac_fail_silently(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = Exception("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_rbac("t1", "admin", {"allowed": True})
        # Should not raise


# ---------------------------------------------------------------------------
# get / set (generic key-value)
# ---------------------------------------------------------------------------


class TestGenericGetSet:
    @patch("app.cache.redis_manager.aioredis")
    async def test_get_returns_value(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.return_value = "my-value"
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get("odoo_mcp:tenant_ds:1")

        assert result == "my-value"
        mock_client.get.assert_awaited_once_with("odoo_mcp:tenant_ds:1")

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_returns_none_on_miss(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get("nonexistent")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_fail_open(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.side_effect = Exception("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get("key")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_stores_value_with_ttl(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set("my-key", "my-value", ttl=300)

        mock_client.set.assert_awaited_once_with("my-key", "my-value", ex=300)

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_default_ttl(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set("key", "val")

        mock_client.set.assert_awaited_once_with("key", "val", ex=3600)

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_fail_silently(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = Exception("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set("key", "val")  # Should not raise


# ---------------------------------------------------------------------------
# build_cache_key
# ---------------------------------------------------------------------------


class TestBuildCacheKey:
    def test_deterministic(self):
        key1 = RedisManager.build_cache_key("a", "b", "c")
        key2 = RedisManager.build_cache_key("a", "b", "c")
        assert key1 == key2

    def test_format_prefix(self):
        key = RedisManager.build_cache_key("foo", "bar")
        assert key.startswith("odoo_mcp:result:")

    def test_md5_content(self):
        key = RedisManager.build_cache_key("foo", "bar")
        raw = "foo|bar"
        expected_digest = hashlib.md5(raw.encode()).hexdigest()
        assert key == f"odoo_mcp:result:{expected_digest}"

    def test_case_insensitive_and_stripped(self):
        key1 = RedisManager.build_cache_key("Foo", " Bar ")
        key2 = RedisManager.build_cache_key("foo", "bar")
        assert key1 == key2

    def test_different_inputs_differ(self):
        key1 = RedisManager.build_cache_key("a", "b")
        key2 = RedisManager.build_cache_key("c", "d")
        assert key1 != key2


# ---------------------------------------------------------------------------
# get_cached_result / set_cached_result
# ---------------------------------------------------------------------------


class TestCachedResult:
    @patch("app.cache.redis_manager.aioredis")
    async def test_get_cached_result_hit(self, mock_aioredis):
        data = {"findings": "ok"}
        mock_client = _make_mock_redis()
        mock_client.get.return_value = json.dumps(data)
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_cached_result("odoo_mcp:result:abc123")

        assert result == data

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_cached_result_miss(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.return_value = None
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_cached_result("odoo_mcp:result:abc123")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_get_cached_result_fail_open(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.get.side_effect = Exception("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        result = await mgr.get_cached_result("odoo_mcp:result:abc123")

        assert result is None

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_cached_result_happy(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_cached_result("odoo_mcp:result:abc", {"x": 1})

        mock_client.set.assert_awaited_once()
        args, kwargs = mock_client.set.call_args
        assert args[0] == "odoo_mcp:result:abc"
        assert json.loads(args[1]) == {"x": 1}

    @patch("app.cache.redis_manager.aioredis")
    async def test_set_cached_result_fail_silently(self, mock_aioredis):
        mock_client = _make_mock_redis()
        mock_client.set.side_effect = Exception("down")
        mock_aioredis.from_url.return_value = mock_client

        mgr = RedisManager("redis://test")
        await mgr.set_cached_result("odoo_mcp:result:abc", {"x": 1})
        # Should not raise
