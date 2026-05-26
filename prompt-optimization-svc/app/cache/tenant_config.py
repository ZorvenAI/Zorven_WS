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

DEFAULT_DATASET_SIZE = 10
MIN_DATASET_SIZE = 3
MAX_DATASET_SIZE = 50


def clamp_ttl(ttl: int) -> int:
    """Clamp TTL to [MIN_TTL, MAX_TTL] inclusive."""
    return max(MIN_TTL, min(MAX_TTL, ttl))


def clamp_dataset_size(size: int) -> int:
    """Clamp dataset size to [MIN_DATASET_SIZE, MAX_DATASET_SIZE] inclusive."""
    return max(MIN_DATASET_SIZE, min(MAX_DATASET_SIZE, size))


class TenantConfigManager:
    """Read/write per-tenant configuration from Redis."""

    CONFIG_KEY_TEMPLATE = "tenant:{tenant_id}:config.prompt_cache_ttl_seconds"
    DATASET_SIZE_KEY_TEMPLATE = "tenant:{tenant_id}:config.golden_dataset_default_size"

    def __init__(self, prompt_cache: PromptCacheManager) -> None:
        self.prompt_cache = prompt_cache

    async def get_prompt_cache_ttl(self, tenant_id: Optional[str] = None) -> int:
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

    async def set_prompt_cache_ttl(self, tenant_id: str, ttl: int) -> None:
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

    async def get_golden_dataset_size(self, tenant_id: Optional[str] = None) -> int:
        """Get the golden dataset size limit for a tenant.

        Returns the tenant-specific size clamped to [3, 50],
        or 10 if no tenant config exists.
        """
        if not tenant_id:
            return DEFAULT_DATASET_SIZE

        try:
            r = await self.prompt_cache.connect()
            key = self.DATASET_SIZE_KEY_TEMPLATE.format(tenant_id=tenant_id)
            value = await r.get(key)
            if value is None:
                return DEFAULT_DATASET_SIZE
            return clamp_dataset_size(int(value))
        except Exception as exc:
            logger.warning(
                "Failed to read tenant dataset size for %s: %s",
                tenant_id,
                exc,
            )
            return DEFAULT_DATASET_SIZE

    async def set_golden_dataset_size(self, tenant_id: str, size: int) -> None:
        """Set the golden dataset size limit for a tenant.

        Value is clamped to [3, 50] before storing (AC-3).
        """
        clamped = clamp_dataset_size(size)
        try:
            r = await self.prompt_cache.connect()
            key = self.DATASET_SIZE_KEY_TEMPLATE.format(tenant_id=tenant_id)
            await r.set(key, str(clamped))
            logger.info(
                "Tenant dataset size set: %s = %d (requested %d)",
                tenant_id,
                clamped,
                size,
            )
        except Exception as exc:
            logger.warning(
                "Failed to set tenant dataset size for %s: %s",
                tenant_id,
                exc,
            )
