"""Tests for TenantRegistry — config loading, register/unregister, list."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.errors import TenantNotFoundError
from app.tenancy.models import TenantConfig
from app.tenancy.registry import TenantRegistry

# ── Fixtures ──


@pytest.fixture
def mock_redis_manager():
    """RedisManager mock with async helpers."""
    rm = MagicMock()
    mock_redis = AsyncMock()
    rm._get_redis = AsyncMock(return_value=mock_redis)
    return rm


@pytest.fixture
def registry(mock_redis_manager):
    return TenantRegistry(redis_manager=mock_redis_manager)


@pytest.fixture
def registry_no_redis():
    return TenantRegistry(redis_manager=None)


@pytest.fixture
def sample_config():
    return TenantConfig(
        tenant_id="acme",
        odoo_url="https://acme.odoo.com",
        odoo_db="acme_prod",
        odoo_username="admin",
        odoo_password="secret",
        plan_tier="professional",
        tenancy_model="dedicated_db",
    )


# ── Default tenant ──


async def test_default_tenant_exists(registry):
    """Default tenant is always registered on init."""
    assert "default" in registry.list_tenants()


async def test_get_default_config(registry):
    config = await registry.get_config("default")
    assert config.tenant_id == "default"
    assert config.odoo_username == "admin"


# ── Register / Unregister ──


async def test_register_and_get(registry, sample_config):
    registry.register(sample_config)

    config = await registry.get_config("acme")
    assert config.tenant_id == "acme"
    assert config.odoo_url == "https://acme.odoo.com"
    assert config.plan_tier == "professional"
    assert config.tenancy_model == "dedicated_db"


async def test_register_overwrites_existing(registry, sample_config):
    registry.register(sample_config)

    updated = sample_config.model_copy(update={"odoo_url": "https://acme-v2.odoo.com"})
    registry.register(updated)

    config = await registry.get_config("acme")
    assert config.odoo_url == "https://acme-v2.odoo.com"


async def test_unregister_removes_tenant(registry, sample_config):
    registry.register(sample_config)
    registry.unregister("acme")
    assert "acme" not in registry.list_tenants()


async def test_unregister_nonexistent_raises(registry):
    with pytest.raises(TenantNotFoundError, match="not registered"):
        registry.unregister("ghost")


async def test_unregister_default_raises(registry):
    with pytest.raises(TenantNotFoundError, match="default"):
        registry.unregister("default")


# ── List tenants ──


async def test_list_tenants(registry, sample_config):
    registry.register(sample_config)
    tenants = registry.list_tenants()
    assert "default" in tenants
    assert "acme" in tenants


async def test_list_tenants_empty_has_default(registry):
    assert registry.list_tenants() == ["default"]


# ── Fallback for unknown tenants ──


async def test_unknown_tenant_falls_back_to_default(registry):
    """Unknown tenant gets default config with the requested tenant_id."""
    config = await registry.get_config("unknown-org")
    assert config.tenant_id == "unknown-org"
    # URL comes from the default config
    default = await registry.get_config("default")
    assert config.odoo_url == default.odoo_url


# ── Redis cache ──


async def test_get_config_reads_from_redis_on_miss(mock_redis_manager):
    """If tenant is not in-memory, try Redis before falling back."""
    cached_config = TenantConfig(
        tenant_id="cached-org",
        odoo_url="https://cached.odoo.com",
        odoo_db="cached_db",
    )
    mock_redis = await mock_redis_manager._get_redis()
    mock_redis.get = AsyncMock(return_value=cached_config.model_dump_json())

    registry = TenantRegistry(redis_manager=mock_redis_manager)
    config = await registry.get_config("cached-org")

    assert config.tenant_id == "cached-org"
    assert config.odoo_url == "https://cached.odoo.com"


async def test_get_config_redis_failure_falls_through(mock_redis_manager):
    """Redis failure is non-fatal — falls back to default config."""
    mock_redis = await mock_redis_manager._get_redis()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("down"))

    registry = TenantRegistry(redis_manager=mock_redis_manager)
    config = await registry.get_config("broken-redis-org")

    # Should still get a valid config (fallback to default)
    assert config.tenant_id == "broken-redis-org"


async def test_write_cache(registry, sample_config, mock_redis_manager):
    """write_cache persists to Redis with TTL."""
    mock_redis = await mock_redis_manager._get_redis()
    mock_redis.set = AsyncMock()

    await registry.write_cache(sample_config)

    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert "acme" in call_args.args[0]


async def test_write_cache_no_redis(registry_no_redis, sample_config):
    """write_cache is a no-op when Redis is not configured."""
    # Should not raise
    await registry_no_redis.write_cache(sample_config)


async def test_get_config_no_redis_falls_back(registry_no_redis):
    """Without Redis, unknown tenants fall back directly to default."""
    config = await registry_no_redis.get_config("no-redis-org")
    assert config.tenant_id == "no-redis-org"
