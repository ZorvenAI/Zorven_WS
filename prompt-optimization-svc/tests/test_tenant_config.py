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
    """Unit tests for set-then-get TTL consistency."""

    async def test_get_after_set_returns_updated_value(
        self, config, mock_redis
    ):
        """Set TTL, then get returns the new value."""
        await config.set_prompt_cache_ttl("tenant-1", 120)

        mock_redis.get.return_value = "120"
        ttl = await config.get_prompt_cache_ttl("tenant-1")
        assert ttl == 120

    async def test_update_takes_effect_immediately(
        self, config, mock_redis
    ):
        """Change from 300 to 60, next read returns 60."""
        mock_redis.get.return_value = "300"
        assert await config.get_prompt_cache_ttl("t-1") == 300

        await config.set_prompt_cache_ttl("t-1", 60)

        mock_redis.get.return_value = "60"
        assert await config.get_prompt_cache_ttl("t-1") == 60


# ------------------------------------------------------------------
# Loader-level integration: tenant TTL in ZorvenPromptLoader (AC-3)
# ------------------------------------------------------------------

from unittest.mock import MagicMock

from app.services.mlflow_registry import PromptInfo
from app.services.prompt_loader import ZorvenPromptLoader


class TestLoaderTenantTTL:
    """AC-3: Tenant TTL change takes effect within one load cycle."""

    async def test_loader_uses_tenant_ttl_on_cache_miss(self):
        """ZorvenPromptLoader resolves TTL from tenant config on Tier 2."""
        mock_cache = AsyncMock()
        mock_cache.get_prompt = AsyncMock(return_value=None)
        mock_cache.set_prompt = AsyncMock()
        mock_cache.connect = AsyncMock()

        mock_registry = MagicMock()
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = "Template"

        mock_tenant_config = AsyncMock()
        mock_tenant_config.get_prompt_cache_ttl = AsyncMock(
            return_value=120
        )

        loader = ZorvenPromptLoader(
            mock_cache, mock_registry, tenant_config=mock_tenant_config
        )
        await loader.load("test", tenant_id="t-1")

        # TTL resolved from tenant config (120s), not default (300s)
        mock_cache.set_prompt.assert_called_once()
        assert mock_cache.set_prompt.call_args[1]["ttl"] == 120

    async def test_loader_uses_explicit_ttl_over_tenant_config(self):
        """Explicit ttl parameter takes precedence over tenant config."""
        mock_cache = AsyncMock()
        mock_cache.get_prompt = AsyncMock(return_value=None)
        mock_cache.set_prompt = AsyncMock()

        mock_registry = MagicMock()
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = "T"

        mock_tenant_config = AsyncMock()
        mock_tenant_config.get_prompt_cache_ttl = AsyncMock(
            return_value=120
        )

        loader = ZorvenPromptLoader(
            mock_cache, mock_registry, tenant_config=mock_tenant_config
        )
        await loader.load("test", tenant_id="t-1", ttl=600)

        # Explicit 600s used, not tenant config 120s
        assert mock_cache.set_prompt.call_args[1]["ttl"] == 600
        mock_tenant_config.get_prompt_cache_ttl.assert_not_called()

    async def test_loader_skips_ttl_resolution_on_cache_hit(self):
        """TTL resolution skipped on Tier 1 cache hit (no extra Redis call)."""
        mock_cache = AsyncMock()
        mock_cache.get_prompt = AsyncMock(return_value="Cached prompt")

        mock_tenant_config = AsyncMock()
        mock_tenant_config.get_prompt_cache_ttl = AsyncMock()

        loader = ZorvenPromptLoader(
            mock_cache, tenant_config=mock_tenant_config
        )
        result = await loader.load("test", tenant_id="t-1")

        assert result == "Cached prompt"
        mock_tenant_config.get_prompt_cache_ttl.assert_not_called()

    async def test_tenant_ttl_change_affects_next_load(self):
        """AC-3: Updating tenant TTL takes effect on the next load cycle."""
        mock_cache = AsyncMock()
        mock_cache.get_prompt = AsyncMock(return_value=None)
        mock_cache.set_prompt = AsyncMock()

        mock_registry = MagicMock()
        mock_registry.get_prompt_by_state.return_value = None
        mock_registry.load_prompt_template.return_value = "T"

        mock_tenant_config = AsyncMock()

        loader = ZorvenPromptLoader(
            mock_cache, mock_registry, tenant_config=mock_tenant_config
        )

        # First load: TTL = 300
        mock_tenant_config.get_prompt_cache_ttl = AsyncMock(
            return_value=300
        )
        await loader.load("test", tenant_id="t-1")
        assert mock_cache.set_prompt.call_args[1]["ttl"] == 300

        mock_cache.set_prompt.reset_mock()

        # Tenant updates TTL to 60 — next load uses 60
        mock_tenant_config.get_prompt_cache_ttl = AsyncMock(
            return_value=60
        )
        await loader.load("test", tenant_id="t-1")
        assert mock_cache.set_prompt.call_args[1]["ttl"] == 60
