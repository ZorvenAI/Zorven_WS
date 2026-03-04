"""Tests for TenantResolver — tenancy models, caching, auth failure."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.errors import OdooAuthenticationError, TenantNotFoundError
from app.tenancy.models import TenantConfig, TenantContext
from app.tenancy.registry import TenantRegistry
from app.tenancy.resolver import TenantResolver

# ── Fixtures ──


@pytest.fixture
def mock_redis_manager():
    rm = MagicMock()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    rm._get_redis = AsyncMock(return_value=mock_redis)
    return rm


@pytest.fixture
def mock_pool():
    """Connection pool mock — returns uid=42 by default."""
    pool = AsyncMock()
    pool.authenticate = AsyncMock(return_value=42)
    return pool


@pytest.fixture
def shared_config():
    return TenantConfig(
        tenant_id="shared-co",
        odoo_url="https://shared.odoo.com",
        odoo_db="shared_db",
        odoo_username="admin",
        odoo_password="pass",
        tenancy_model="shared_instance",
        company_id=3,
    )


@pytest.fixture
def dedicated_config():
    return TenantConfig(
        tenant_id="dedicated-co",
        odoo_url="https://dedicated.odoo.com",
        odoo_db="dedicated_db",
        odoo_username="admin",
        odoo_password="pass",
        tenancy_model="dedicated_db",
        company_id=1,
    )


@pytest.fixture
def shared_db_config():
    return TenantConfig(
        tenant_id="shared-db-co",
        odoo_url="https://shared-db.odoo.com",
        odoo_db="common_db",
        odoo_username="admin",
        odoo_password="pass",
        tenancy_model="shared_db",
        company_id=5,
    )


@pytest.fixture
def registry_with_configs(shared_config, dedicated_config, shared_db_config):
    registry = TenantRegistry(redis_manager=None)
    registry.register(shared_config)
    registry.register(dedicated_config)
    registry.register(shared_db_config)
    return registry


@pytest.fixture
def resolver(registry_with_configs, mock_pool, mock_redis_manager):
    return TenantResolver(
        registry=registry_with_configs,
        connection_pool=mock_pool,
        redis_manager=mock_redis_manager,
    )


@pytest.fixture
def resolver_no_redis(registry_with_configs, mock_pool):
    return TenantResolver(
        registry=registry_with_configs,
        connection_pool=mock_pool,
        redis_manager=None,
    )


# ── Tenancy model: shared_instance ──


async def test_resolve_shared_instance(resolver, mock_pool):
    """shared_instance uses the configured odoo_db directly."""
    ctx = await resolver.resolve("shared-co")

    assert ctx.authenticated is True
    assert ctx.odoo_uid == 42
    assert ctx.company_id == 3
    assert ctx.config.tenant_id == "shared-co"

    mock_pool.authenticate.assert_called_once_with(
        url="https://shared.odoo.com",
        db="shared_db",
        username="admin",
        password="pass",
    )


# ── Tenancy model: dedicated_db ──


async def test_resolve_dedicated_db(resolver, mock_pool):
    """dedicated_db computes the DB name as '<tenant_id>_db'."""
    ctx = await resolver.resolve("dedicated-co")

    assert ctx.authenticated is True
    assert ctx.odoo_uid == 42

    mock_pool.authenticate.assert_called_once_with(
        url="https://dedicated.odoo.com",
        db="dedicated-co_db",
        username="admin",
        password="pass",
    )


# ── Tenancy model: shared_db ──


async def test_resolve_shared_db(resolver, mock_pool):
    """shared_db uses the configured odoo_db (same as shared_instance)."""
    ctx = await resolver.resolve("shared-db-co")

    assert ctx.authenticated is True
    assert ctx.company_id == 5

    mock_pool.authenticate.assert_called_once_with(
        url="https://shared-db.odoo.com",
        db="common_db",
        username="admin",
        password="pass",
    )


# ── Authentication failures ──


async def test_auth_failure_uid_zero(resolver, mock_pool):
    """uid=0 from Odoo means auth failed."""
    mock_pool.authenticate.return_value = 0

    with pytest.raises(OdooAuthenticationError, match="uid=0"):
        await resolver.resolve("shared-co")


async def test_auth_failure_exception(resolver, mock_pool):
    """Unexpected exception during auth is wrapped in OdooAuthenticationError."""
    mock_pool.authenticate.side_effect = ConnectionError("network down")

    with pytest.raises(OdooAuthenticationError, match="Authentication failed"):
        await resolver.resolve("shared-co")


async def test_auth_failure_explicit_error(resolver, mock_pool):
    """OdooAuthenticationError from the pool is re-raised directly."""
    mock_pool.authenticate.side_effect = OdooAuthenticationError("bad creds")

    with pytest.raises(OdooAuthenticationError, match="bad creds"):
        await resolver.resolve("shared-co")


# ── Caching ──


async def test_cached_context_returned(resolver, mock_redis_manager, shared_config):
    """If Redis has a cached context, the pool is never called."""
    cached_ctx = TenantContext(
        config=shared_config,
        odoo_uid=99,
        company_id=3,
        authenticated=True,
    )
    mock_redis = await mock_redis_manager._get_redis()
    mock_redis.get = AsyncMock(return_value=cached_ctx.model_dump_json())

    # Re-create resolver so it picks up the new mock behavior
    registry = TenantRegistry(redis_manager=None)
    registry.register(shared_config)
    pool = AsyncMock()
    pool.authenticate = AsyncMock(return_value=42)
    resolver = TenantResolver(
        registry=registry,
        connection_pool=pool,
        redis_manager=mock_redis_manager,
    )

    ctx = await resolver.resolve("shared-co")
    assert ctx.odoo_uid == 99
    # Pool should NOT have been called — cache hit
    pool.authenticate.assert_not_called()


async def test_resolved_context_is_cached(resolver, mock_redis_manager):
    """After resolving, the context is written to Redis."""
    mock_redis = await mock_redis_manager._get_redis()

    await resolver.resolve("shared-co")

    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    assert "shared-co" in call_args.args[0]


async def test_redis_cache_failure_non_fatal(mock_redis_manager, mock_pool):
    """Redis read failure does not prevent resolution."""
    mock_redis = await mock_redis_manager._get_redis()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("down"))
    mock_redis.set = AsyncMock(side_effect=ConnectionError("down"))

    registry = TenantRegistry(redis_manager=None)
    resolver = TenantResolver(
        registry=registry,
        connection_pool=mock_pool,
        redis_manager=mock_redis_manager,
    )

    # Should succeed using fallback config + pool auth
    ctx = await resolver.resolve("any-tenant")
    assert ctx.authenticated is True
    assert ctx.odoo_uid == 42


# ── No Redis ──


async def test_resolve_without_redis(resolver_no_redis, mock_pool):
    """Resolver works fine without Redis configured."""
    ctx = await resolver_no_redis.resolve("shared-co")

    assert ctx.authenticated is True
    assert ctx.odoo_uid == 42


# ── Database name resolution ──


def test_resolve_database_dedicated():
    config = TenantConfig(
        tenant_id="my-tenant",
        odoo_url="http://localhost:8069",
        odoo_db="ignored",
        tenancy_model="dedicated_db",
    )
    assert TenantResolver._resolve_database(config) == "my-tenant_db"


def test_resolve_database_shared_instance():
    config = TenantConfig(
        tenant_id="my-tenant",
        odoo_url="http://localhost:8069",
        odoo_db="production",
        tenancy_model="shared_instance",
    )
    assert TenantResolver._resolve_database(config) == "production"


def test_resolve_database_shared_db():
    config = TenantConfig(
        tenant_id="my-tenant",
        odoo_url="http://localhost:8069",
        odoo_db="common",
        tenancy_model="shared_db",
    )
    assert TenantResolver._resolve_database(config) == "common"
