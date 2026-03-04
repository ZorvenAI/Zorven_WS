"""Per-tenant connection pool for OdooRPCClient instances.

Maintains a cache of authenticated clients keyed by tenant_id so that
repeated calls from the same tenant reuse an existing session instead
of re-authenticating on every request.  Thread-safe via asyncio.Lock.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from app.services.odoo_rpc_client import OdooRPCClient

logger = logging.getLogger(__name__)


@dataclass
class _PoolEntry:
    """Internal bookkeeping for a pooled client."""

    client: OdooRPCClient
    url: str
    db: str
    username: str


class TenantConnectionPool:
    """Manages per-tenant OdooRPCClient instances with lazy auth."""

    def __init__(
        self,
        default_pool_size: int = 5,
        max_pool_size: int = 20,
    ) -> None:
        self._default_pool_size = default_pool_size
        self._max_pool_size = max_pool_size
        self._pool: dict[str, _PoolEntry] = {}
        self._lock = asyncio.Lock()

    async def get_client(
        self,
        tenant_id: str,
        url: str,
        db: str,
        username: str,
        password: str,
    ) -> OdooRPCClient:
        """Return a cached client for *tenant_id*, creating one if needed.

        If the cached client's connection parameters differ from the
        ones supplied, the old entry is evicted and a fresh client is
        created and authenticated.
        """
        async with self._lock:
            entry = self._pool.get(tenant_id)

            if entry is not None:
                # Validate that cached params still match
                if entry.url == url and entry.db == db and entry.username == username:
                    return entry.client

                # Parameters changed — evict stale entry
                logger.info(
                    "Evicting stale pool entry for tenant %s "
                    "(connection params changed)",
                    tenant_id,
                )
                del self._pool[tenant_id]

            # Enforce max pool size
            if len(self._pool) >= self._max_pool_size:
                oldest_key = next(iter(self._pool))
                logger.warning(
                    "Pool at max capacity (%d) — evicting tenant %s",
                    self._max_pool_size,
                    oldest_key,
                )
                del self._pool[oldest_key]

            # Create + authenticate a new client
            client = OdooRPCClient(url=url, db=db, username=username, password=password)
            await client.authenticate()

            self._pool[tenant_id] = _PoolEntry(
                client=client, url=url, db=db, username=username
            )
            logger.info(
                "Created pool entry for tenant %s (pool size: %d)",
                tenant_id,
                len(self._pool),
            )
            return client

    async def release_client(self, tenant_id: str) -> None:
        """Remove a single tenant's client from the pool."""
        async with self._lock:
            if tenant_id in self._pool:
                del self._pool[tenant_id]
                logger.info("Released pool entry for tenant %s", tenant_id)

    async def close_all(self) -> None:
        """Remove all clients from the pool."""
        async with self._lock:
            count = len(self._pool)
            self._pool.clear()
            logger.info("Closed all pool entries (%d removed)", count)

    def get_pool_stats(self) -> dict:
        """Return ``{tenant_id: 1}`` for each tenant in the pool.

        Useful for health / monitoring endpoints.
        """
        return {tid: 1 for tid in self._pool}
