"""Tenant-configurable prompt cache TTL (§10.2).

Redis key: tenant:<tid>:config.prompt_cache_ttl_seconds
Clamped to [10, 3600] with 300s default.
"""

import logging
from typing import Optional

from app.cache.prompt_cache import PromptCacheManager

logger = logging.getLogger(__name__)

DEFAULT_TTL = 300
MIN_TTL = 10
MAX_TTL = 3600


def clamp_ttl(ttl: int) -> int:
    """Clamp TTL to [MIN_TTL, MAX_TTL] inclusive."""
    return max(MIN_TTL, min(MAX_TTL, ttl))


class TenantConfigManager:
    """Read/write per-tenant configuration from Redis."""

    CONFIG_KEY_TEMPLATE = "tenant:{tenant_id}:config.prompt_cache_ttl_seconds"

    def __init__(self, prompt_cache: PromptCacheManager) -> None:
        self.prompt_cache = prompt_cache

    async def get_prompt_cache_ttl(
        self, tenant_id: Optional[str] = None
    ) -> int:
        """Get the prompt cache TTL for a tenant.

        Returns the tenant-specific TTL clamped to [10, 3600],
        or 300s if no tenant config exists (AC-2).
        """
        if not tenant_id:
            return DEFAULT_TTL

        try:
            r = await self.prompt_cache.connect()
            key = self.CONFIG_KEY_TEMPLATE.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return DEFAULT_TTL
            return clamp_ttl(int(value))
        except Exception as exc:
            logger.warning(
                "Failed to read tenant TTL config for %s: %s",
                tenant_id,
                exc,
            )
            return DEFAULT_TTL

    async def set_prompt_cache_ttl(
        self, tenant_id: str, ttl: int
    ) -> None:
        """Set the prompt cache TTL for a tenant.

        Value is clamped to [10, 3600] before storing (AC-1).
        """
        clamped = clamp_ttl(ttl)
        try:
            r = await self.prompt_cache.connect()
            key = self.CONFIG_KEY_TEMPLATE.format(tenant_id=tenant_id)
            await r.set(key, str(clamped))
            logger.info(
                "Tenant TTL config set: %s = %ds (requested %ds)",
                tenant_id,
                clamped,
                ttl,
            )
        except Exception as exc:
            logger.warning(
                "Failed to set tenant TTL config for %s: %s",
                tenant_id,
                exc,
            )
