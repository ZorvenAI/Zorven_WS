"""Tenant → Vertex AI data store resolver.

Reads tenants_tenant.vertex_ai_data_store_id from Neon DB (read-only).
Caches results in Redis DB 9 with 1-hour TTL.
"""

import logging
from typing import Optional

from app.cache.redis_manager import RedisManager
from app.core.config import settings

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "odoo_mcp:tenant_ds"
CACHE_TTL = 3600  # 1 hour


class TenantDataStoreResolver:
    """Resolves tenant_id → Vertex AI data store ID via Neon DB."""

    def __init__(
        self,
        database_url: str,
        redis_manager: Optional[RedisManager] = None,
        default_data_store_id: Optional[str] = None,
    ) -> None:
        self.database_url = database_url
        self.redis_manager = redis_manager
        self.default_data_store_id = (
            default_data_store_id or settings.VERTEX_AI_DATA_STORE_ID
        )
        self._pool = None

    async def init(self) -> None:
        """Create asyncpg connection pool."""
        if not self.database_url:
            logger.warning("DATABASE_URL not set — tenant resolver disabled")
            return

        try:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=3,
                command_timeout=10,
            )
            logger.info("TenantDataStoreResolver pool initialized")
        except Exception as exc:
            logger.warning("Failed to create asyncpg pool: %s", exc)
            self._pool = None

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def resolve_data_store_id(self, tenant_id: str) -> str:
        """Resolve tenant_id → Vertex AI data store ID.

        Lookup order:
        1. Redis cache (key: odoo_mcp:tenant_ds:{tenant_id}, TTL 1h)
        2. Neon DB query (tenants_tenant.vertex_ai_data_store_id)
        3. Fall back to configured default
        """
        # 1. Check Redis cache
        cached = await self._get_cached(tenant_id)
        if cached:
            return cached

        # 2. Query Neon DB
        data_store_id = await self._query_db(tenant_id)
        if data_store_id:
            await self._set_cached(tenant_id, data_store_id)
            return data_store_id

        # 3. Fallback to default
        return self.default_data_store_id

    async def _get_cached(self, tenant_id: str) -> Optional[str]:
        """Check Redis cache for tenant data store mapping."""
        if self.redis_manager is None:
            return None
        try:
            key = f"{CACHE_KEY_PREFIX}:{tenant_id}"
            value = await self.redis_manager.get(key)
            if value:
                logger.debug("Cache hit for tenant %s: %s", tenant_id, value)
                return value
        except Exception as exc:
            logger.debug("Redis cache read failed: %s", exc)
        return None

    async def _set_cached(self, tenant_id: str, data_store_id: str) -> None:
        """Cache tenant → data store mapping in Redis."""
        if self.redis_manager is None:
            return
        try:
            key = f"{CACHE_KEY_PREFIX}:{tenant_id}"
            await self.redis_manager.set(key, data_store_id, ttl=CACHE_TTL)
        except Exception as exc:
            logger.debug("Redis cache write failed: %s", exc)

    async def _query_db(self, tenant_id: str) -> Optional[str]:
        """Query Neon DB for tenant's data store ID."""
        if self._pool is None:
            return None

        try:
            tenant_pk = int(tenant_id)
        except (ValueError, TypeError):
            logger.debug("Non-numeric tenant_id: %s", tenant_id)
            return None

        try:
            row = await self._pool.fetchrow(
                "SELECT vertex_ai_data_store_id FROM tenants_tenant WHERE id = $1",
                tenant_pk,
            )
            if row and row["vertex_ai_data_store_id"]:
                logger.debug(
                    "DB resolved tenant %s → %s",
                    tenant_id,
                    row["vertex_ai_data_store_id"],
                )
                return row["vertex_ai_data_store_id"]
        except Exception as exc:
            logger.warning("DB lookup failed for tenant %s: %s", tenant_id, exc)

        return None
