"""Tests for tenant-configurable cache TTL (§10.2)."""

from unittest.mock import AsyncMock

import pytest

from app.cache.tenant_config import (
    DEFAULT_TTL,
    MAX_TTL,
    MIN_TTL,
    TenantConfigManager,
    clamp_ttl,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    r = AsyncMock()
    r.get.return_value = None
    r.set.return_value = True
    return r


@pytest.fixture
def mock_cache(mock_redis):
    """Mock PromptCacheManager with Redis client."""
    cache = AsyncMock()
    cache.connect.return_value = mock_redis
    return cache


@pytest.fixture
def config(mock_cache):
    """TenantConfigManager with mocked cache."""
    return TenantConfigManager(mock_cache)


# ------------------------------------------------------------------
# clamp_ttl (AC-1)
# ------------------------------------------------------------------


class TestClampTTL:
    """TTL is clamped to [10, 3600] inclusive (AC-1)."""

    def test_below_min_clamped_to_10(self):
        assert clamp_ttl(5) == MIN_TTL

    def test_zero_clamped_to_10(self):
        assert clamp_ttl(0) == MIN_TTL

    def test_negative_clamped_to_10(self):
        assert clamp_ttl(-100) == MIN_TTL

    def test_above_max_clamped_to_3600(self):
        assert clamp_ttl(5000) == MAX_TTL

    def test_exactly_min_accepted(self):
        assert clamp_ttl(10) == 10

    def test_exactly_max_accepted(self):
        assert clamp_ttl(3600) == 3600

    def test_within_range_passes_through(self):
        assert clamp_ttl(600) == 600

    def test_default_value(self):
        assert clamp_ttl(300) == 300

    def test_constants(self):
        assert MIN_TTL == 10
        assert MAX_TTL == 3600
        assert DEFAULT_TTL == 300


# ------------------------------------------------------------------
# get_prompt_cache_ttl (AC-2)
# ------------------------------------------------------------------


class TestGetTTL:
    """Get tenant TTL with default fallback (AC-2)."""

    async def test_missing_config_returns_default(self, config, mock_redis):
        """AC-2: Missing tenant config falls back to 300s."""
        mock_redis.get.return_value = None
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == DEFAULT_TTL

    async def test_none_tenant_returns_default(self, config):
        """None tenant_id returns default without Redis call."""
        ttl = await config.get_prompt_cache_ttl(None)
        assert ttl == DEFAULT_TTL

    async def test_empty_tenant_returns_default(self, config):
        ttl = await config.get_prompt_cache_ttl("")
        assert ttl == DEFAULT_TTL

    async def test_stored_value_returned(self, config, mock_redis):
        mock_redis.get.return_value = "600"
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == 600

    async def test_stored_value_clamped_below_min(self, config, mock_redis):
        """AC-1: Stored value below 10 is clamped."""
        mock_redis.get.return_value = "5"
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == MIN_TTL

    async def test_stored_value_clamped_above_max(self, config, mock_redis):
        """AC-1: Stored value above 3600 is clamped."""
        mock_redis.get.return_value = "9999"
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == MAX_TTL

    async def test_redis_error_returns_default(self, config, mock_redis):
        mock_redis.get.side_effect = ConnectionError("refused")
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == DEFAULT_TTL

    async def test_correct_redis_key_used(self, config, mock_redis):
        await config.get_prompt_cache_ttl("t-42")
        mock_redis.get.assert_called_once_with(
            "tenant:t-42:config.prompt_cache_ttl_seconds"
        )


# ------------------------------------------------------------------
# set_prompt_cache_ttl
# ------------------------------------------------------------------


class TestSetTTL:
    """Set tenant TTL with clamping."""

    async def test_set_within_range(self, config, mock_redis):
        await config.set_prompt_cache_ttl("tenant-1", 600)
        mock_redis.set.assert_called_once_with(
            "tenant:tenant-1:config.prompt_cache_ttl_seconds", "600"
        )

    async def test_set_below_min_clamped(self, config, mock_redis):
        """AC-1: Value below 10 stored as 10."""
        await config.set_prompt_cache_ttl("tenant-1", 5)
        mock_redis.set.assert_called_once_with(
            "tenant:tenant-1:config.prompt_cache_ttl_seconds", "10"
        )

    async def test_set_above_max_clamped(self, config, mock_redis):
        """AC-1: Value above 3600 stored as 3600."""
        await config.set_prompt_cache_ttl("tenant-1", 5000)
        mock_redis.set.assert_called_once_with(
            "tenant:tenant-1:config.prompt_cache_ttl_seconds", "3600"
        )

    async def test_set_boundary_min(self, config, mock_redis):
        await config.set_prompt_cache_ttl("t-1", 10)
        mock_redis.set.assert_called_once_with(
            "tenant:t-1:config.prompt_cache_ttl_seconds", "10"
        )

    async def test_set_boundary_max(self, config, mock_redis):
        await config.set_prompt_cache_ttl("t-1", 3600)
        mock_redis.set.assert_called_once_with(
            "tenant:t-1:config.prompt_cache_ttl_seconds", "3600"
        )


# ------------------------------------------------------------------
# Integration: set then get (AC-3)
# ------------------------------------------------------------------


class TestSetThenGet:
    """AC-3: Updating config takes effect within one load cycle."""

    async def test_get_after_set_returns_updated_value(
        self, config, mock_redis
    ):
        """AC-3: Set TTL, then get returns the new value."""
        # Set TTL to 120s
        await config.set_prompt_cache_ttl("tenant-1", 120)

        # Simulate Redis returning the stored value on next get
        mock_redis.get.return_value = "120"
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == 120

    async def test_update_takes_effect_immediately(
        self, config, mock_redis
    ):
        """AC-3: Change from 300 to 60, next read returns 60."""
        # Initial state: 300
        mock_redis.get.return_value = "300"
        assert await config.get_prompt_cache_ttl("t-1") == 300

        # Update to 60
        await config.set_prompt_cache_ttl("t-1", 60)

        # Next read returns 60
        mock_redis.get.return_value = "60"
        assert await config.get_prompt_cache_ttl("t-1") == 60
