"""Tenant resolver — authenticates tenants against Odoo and builds context.

Handles three tenancy models:
- **dedicated_db**: each tenant has its own Odoo database.
- **shared_instance**: tenants share the Odoo instance but are isolated by
  company_id (multi-company).
- **shared_db**: single database, row-level isolation only.
"""

import json
import logging
from typing import Optional, Protocol

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.services.errors import OdooAuthenticationError, TenantNotFoundError
from app.tenancy.models import TenantConfig, TenantContext
from app.tenancy.registry import TenantRegistry

logger = logging.getLogger(__name__)

_CONTEXT_CACHE_PREFIX = "odoo_mcp:tenant_context"


class TenantConnectionPool(Protocol):
    """Protocol for the Odoo connection pool used by the resolver.

    Implementations must provide an ``authenticate`` method that validates
    credentials against a running Odoo instance and returns the user ID.
    """

    async def authenticate(
        self,
        url: str,
        db: str,
        username: str,
        password: str,
    ) -> int:
        """Authenticate against Odoo and return uid (0 on failure)."""
        ...  # pragma: no cover


class TenantResolver:
    """Resolves a tenant ID into a fully authenticated TenantContext."""

    def __init__(
        self,
        registry: TenantRegistry,
        connection_pool: TenantConnectionPool,
        redis_manager: Optional[RedisManager] = None,
    ) -> None:
        self._registry = registry
        self._pool = connection_pool
        self._redis = redis_manager

    async def resolve(self, tenant_id: str) -> TenantContext:
        """Build an authenticated TenantContext for *tenant_id*.

        Steps
        -----
        1. Check Redis cache for a previously resolved context.
        2. Load tenant config from the registry.
        3. Determine Odoo database from tenancy model.
        4. Authenticate via the connection pool.
        5. Cache the resulting context in Redis.
        """
        # 1. Check cache
        cached = await self._read_cached_context(tenant_id)
        if cached is not None:
            return cached

        # 2. Load config
        config = await self._registry.get_config(tenant_id)

        # 3. Resolve Odoo DB depending on tenancy model
        odoo_db = self._resolve_database(config)

        # 4. Authenticate
        uid = await self._authenticate(config, odoo_db)

        # 5. Build context
        context = TenantContext(
            config=config,
            odoo_uid=uid,
            company_id=config.company_id,
            authenticated=True,
        )

        # 6. Cache
        await self._write_cached_context(tenant_id, context)

        logger.info(
            "Resolved tenant %s (uid=%d, model=%s, db=%s)",
            tenant_id,
            uid,
            config.tenancy_model,
            odoo_db,
        )
        return context

    # ── Internal helpers ──

    @staticmethod
    def _resolve_database(config: TenantConfig) -> str:
        """Determine the Odoo database name based on tenancy model.

        - dedicated_db  : ``<tenant_id>_db``
        - shared_instance: the configured ``odoo_db`` (all tenants share it)
        - shared_db      : same as shared_instance (isolation is row-level)
        """
        if config.tenancy_model == "dedicated_db":
            return f"{config.tenant_id}_db"
        # shared_instance and shared_db both use the configured db
        return config.odoo_db

    async def _authenticate(self, config: TenantConfig, odoo_db: str) -> int:
        """Authenticate with Odoo via the connection pool.

        Raises OdooAuthenticationError if uid is 0 / falsy.
        """
        try:
            uid = await self._pool.authenticate(
                url=config.odoo_url,
                db=odoo_db,
                username=config.odoo_username,
                password=config.odoo_password,
            )
        except OdooAuthenticationError:
            raise
        except Exception as exc:
            logger.error(
                "Odoo authentication failed for tenant %s: %s",
                config.tenant_id,
                exc,
            )
            raise OdooAuthenticationError(
                f"Authentication failed for tenant '{config.tenant_id}'"
            ) from exc

        if not uid:
            raise OdooAuthenticationError(
                f"Authentication failed for tenant '{config.tenant_id}' " f"(uid=0)"
            )
        return uid

    # ── Redis cache helpers (fail-open) ──

    async def _read_cached_context(self, tenant_id: str) -> Optional[TenantContext]:
        if self._redis is None:
            return None
        try:
            r = await self._redis._get_redis()
            key = f"{_CONTEXT_CACHE_PREFIX}:{tenant_id}"
            data = await r.get(key)
            if data:
                logger.debug("Tenant context cache hit for %s", tenant_id)
                return TenantContext.model_validate_json(data)
        except Exception:
            logger.warning("Redis tenant context read failed for %s", tenant_id)
        return None

    async def _write_cached_context(
        self, tenant_id: str, context: TenantContext
    ) -> None:
        if self._redis is None:
            return
        try:
            r = await self._redis._get_redis()
            key = f"{_CONTEXT_CACHE_PREFIX}:{tenant_id}"
            await r.set(
                key,
                context.model_dump_json(),
                ex=settings.TENANT_CACHE_TTL,
            )
        except Exception:
            logger.warning("Redis tenant context write failed for %s", tenant_id)
