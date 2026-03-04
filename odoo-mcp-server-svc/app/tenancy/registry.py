"""Tenant registry — stores and retrieves per-tenant Odoo configurations.

Configs live in an in-memory dict with optional Redis caching (fail-open).
A default tenant is always available, seeded from global settings.
"""

import json
import logging
from typing import Optional

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.services.errors import TenantNotFoundError
from app.tenancy.models import TenantConfig

logger = logging.getLogger(__name__)

_REDIS_KEY_PREFIX = "odoo_mcp:tenant_config"


class TenantRegistry:
    """In-memory tenant config store backed by optional Redis cache."""

    def __init__(self, redis_manager: Optional[RedisManager] = None) -> None:
        self._redis = redis_manager
        self._tenants: dict[str, TenantConfig] = {}

        # Seed the default tenant from global settings
        default = TenantConfig(
            tenant_id="default",
            odoo_url=settings.ODOO_URL,
            odoo_db="odoo",
            odoo_username="admin",
            odoo_password=settings.ODOO_MASTER_PASSWORD,
            tenancy_model=settings.TENANT_MODEL,
            pool_size=settings.POOL_SIZE_DEFAULT,
            rate_limit=settings.RATE_LIMIT_PER_MINUTE,
        )
        self._tenants["default"] = default

    # ── Public API ──

    async def get_config(self, tenant_id: str) -> TenantConfig:
        """Return config for *tenant_id*.

        Lookup order:
        1. In-memory dict
        2. Redis cache
        3. Fall back to default config with the requested tenant_id

        Raises TenantNotFoundError only if the tenant was explicitly
        unregistered (i.e. not simply absent — absent tenants get the
        default config).
        """
        # 1. In-memory
        if tenant_id in self._tenants:
            return self._tenants[tenant_id]

        # 2. Redis cache
        cached = await self._read_cache(tenant_id)
        if cached is not None:
            self._tenants[tenant_id] = cached
            return cached

        # 3. Fall back to default config, scoped to the requested tenant_id
        logger.info("Tenant %s not registered — using default config", tenant_id)
        default = self._tenants["default"]
        fallback = default.model_copy(update={"tenant_id": tenant_id})
        return fallback

    def register(self, config: TenantConfig) -> None:
        """Add or update a tenant config."""
        self._tenants[config.tenant_id] = config
        logger.info("Registered tenant %s", config.tenant_id)

    def unregister(self, tenant_id: str) -> None:
        """Remove a tenant config.

        Raises TenantNotFoundError if the tenant is not registered.
        The 'default' tenant cannot be unregistered.
        """
        if tenant_id == "default":
            raise TenantNotFoundError("Cannot unregister the default tenant")
        if tenant_id not in self._tenants:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' is not registered")
        del self._tenants[tenant_id]
        logger.info("Unregistered tenant %s", tenant_id)

    def list_tenants(self) -> list[str]:
        """Return all registered tenant IDs."""
        return list(self._tenants.keys())

    # ── Redis helpers (fail-open) ──

    async def _read_cache(self, tenant_id: str) -> Optional[TenantConfig]:
        """Try to read tenant config from Redis. Returns None on miss/error."""
        if self._redis is None:
            return None
        try:
            r = await self._redis._get_redis()
            key = f"{_REDIS_KEY_PREFIX}:{tenant_id}"
            data = await r.get(key)
            if data:
                return TenantConfig.model_validate_json(data)
        except Exception:
            logger.warning("Redis tenant config read failed for %s", tenant_id)
        return None

    async def write_cache(self, config: TenantConfig) -> None:
        """Persist tenant config to Redis with configured TTL."""
        if self._redis is None:
            return
        try:
            r = await self._redis._get_redis()
            key = f"{_REDIS_KEY_PREFIX}:{config.tenant_id}"
            await r.set(
                key,
                config.model_dump_json(),
                ex=settings.TENANT_CACHE_TTL,
            )
        except Exception:
            logger.warning("Redis tenant config write failed for %s", config.tenant_id)
