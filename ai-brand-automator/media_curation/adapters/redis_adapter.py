"""
Redis Adapter - Redis implementation of CachePort.

Handles status tracking, tenant config caching, and event deduplication
for the curation pipeline.
"""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import UUID

from django.conf import settings

from media_curation.ports.cache_port import CachePort
from media_curation.domain.models import (
    CurationStatus,
    CurationStatusRecord,
    TenantConfig,
)
from media_curation.domain.exceptions import CacheError


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=4)


class RedisAdapter(CachePort):
    """
    Redis adapter implementing CachePort.

    Uses redis-py for all Redis operations.
    Supports status tracking, tenant config caching, and deduplication.
    """

    # Key prefixes for organization
    STATUS_PREFIX = "curation:status:"
    TENANT_PREFIX = "curation:tenant:"
    DEDUPE_PREFIX = "curation:dedupe:"

    # Default TTLs
    DEFAULT_STATUS_TTL = 604800  # 7 days
    DEFAULT_TENANT_TTL = 3600  # 1 hour
    DEFAULT_DEDUPE_TTL = 86400  # 24 hours

    def __init__(
        self,
        redis_url: Optional[str] = None,
        status_ttl_seconds: int = DEFAULT_STATUS_TTL,
        tenant_ttl_seconds: int = DEFAULT_TENANT_TTL,
        dedupe_ttl_seconds: int = DEFAULT_DEDUPE_TTL,
    ):
        """
        Initialize the Redis adapter.

        Args:
            redis_url: Redis connection URL (uses settings if not provided)
            status_ttl_seconds: TTL for status records
            tenant_ttl_seconds: TTL for tenant config cache
            dedupe_ttl_seconds: TTL for deduplication keys
        """
        # Lazy import to avoid issues when redis is not installed
        try:
            import redis

            self._redis_available = True
        except ImportError:
            self._redis_available = False
            logger.warning("redis not installed, using in-memory mock")
            self.client = None
            self._memory_cache = {}
            return

        self.status_ttl = status_ttl_seconds
        self.tenant_ttl = tenant_ttl_seconds
        self.dedupe_ttl = dedupe_ttl_seconds

        # Get Redis URL from settings
        cache_config = getattr(settings, "MEDIA_CURATION", {}).get("CACHE", {})
        url = redis_url or cache_config.get("REDIS_URL", "redis://localhost:6379/0")

        try:
            self.client = redis.from_url(url, decode_responses=True)
            # Test connection
            self.client.ping()
            logger.info("Redis adapter initialized", extra={"url": self._mask_url(url)})
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory mock: {e}")
            self._redis_available = False
            self.client = None
            self._memory_cache = {}

    @staticmethod
    def _mask_url(url: str) -> str:
        """Mask password in Redis URL for logging."""
        if "@" in url:
            prefix, rest = url.split("@", 1)
            return f"{prefix.rsplit(':', 1)[0]}:***@{rest}"
        return url

    def _status_key(self, trace_id: str) -> str:
        """Generate status tracking key."""
        return f"{self.STATUS_PREFIX}{trace_id}"

    def _tenant_key(self, tenant_id: str) -> str:
        """Generate tenant config key."""
        return f"{self.TENANT_PREFIX}{tenant_id}"

    def _dedupe_key(self, event_id: str) -> str:
        """Generate deduplication key."""
        return f"{self.DEDUPE_PREFIX}{event_id}"

    def _serialize_status(self, status: CurationStatusRecord) -> str:
        """Serialize status record to JSON."""
        return json.dumps(
            {
                "trace_id": str(status.trace_id),
                "event_id": str(status.event_id),
                "tenant_id": status.tenant_id,
                "file_id": str(status.file_id),
                "status": status.status.value,
                "message": status.message,
                "output_gcs_uri": status.output_gcs_uri,
                "error_code": status.error_code,
                "updated_at": status.updated_at.isoformat(),
            }
        )

    def _deserialize_status(self, data: str) -> CurationStatusRecord:
        """Deserialize JSON to status record."""
        d = json.loads(data)
        return CurationStatusRecord(
            trace_id=UUID(d["trace_id"]),
            event_id=UUID(d["event_id"]),
            tenant_id=d["tenant_id"],
            file_id=UUID(d["file_id"]),
            status=CurationStatus(d["status"]),
            message=d.get("message"),
            output_gcs_uri=d.get("output_gcs_uri"),
            error_code=d.get("error_code"),
            updated_at=datetime.fromisoformat(d["updated_at"]),
        )

    def _serialize_tenant_config(self, config: TenantConfig) -> str:
        """Serialize tenant config to JSON."""
        return json.dumps(
            {
                "tenant_id": config.tenant_id,
                "dlp_enabled": config.dlp_enabled,
                "dlp_info_types": config.dlp_info_types,
                "ai_model": config.ai_model,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }
        )

    def _deserialize_tenant_config(self, data: str) -> TenantConfig:
        """Deserialize JSON to tenant config."""
        d = json.loads(data)
        return TenantConfig(
            tenant_id=d["tenant_id"],
            dlp_enabled=d.get("dlp_enabled", True),
            dlp_info_types=d.get("dlp_info_types", []),
            ai_model=d.get("ai_model", "gemini-2.0-flash"),
            max_tokens=d.get("max_tokens", 8192),
            temperature=d.get("temperature", 0.1),
        )

    # Status tracking

    async def get_status(self, trace_id: str) -> Optional[CurationStatusRecord]:
        """Get curation status for a trace_id."""
        key = self._status_key(trace_id)

        if not self._redis_available:
            data = self._memory_cache.get(key)
            return self._deserialize_status(data) if data else None

        def _get():
            try:
                data = self.client.get(key)
                return self._deserialize_status(data) if data else None
            except Exception as e:
                logger.error(f"Redis get_status error: {e}")
                raise CacheError(f"Failed to get status: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get)

    async def set_status(
        self,
        trace_id: str,
        status: CurationStatusRecord,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store curation status."""
        key = self._status_key(trace_id)
        data = self._serialize_status(status)
        ttl = ttl_seconds or self.status_ttl

        if not self._redis_available:
            self._memory_cache[key] = data
            return

        def _set():
            try:
                self.client.setex(key, ttl, data)
            except Exception as e:
                logger.error(f"Redis set_status error: {e}")
                raise CacheError(f"Failed to set status: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _set)

    async def update_status(
        self,
        trace_id: str,
        status: CurationStatus,
        **updates: Any,
    ) -> None:
        """Update status fields for existing record."""
        existing = await self.get_status(trace_id)
        if not existing:
            logger.warning(f"No existing status for trace_id: {trace_id}")
            return

        # Create updated record
        updated = CurationStatusRecord(
            trace_id=existing.trace_id,
            event_id=existing.event_id,
            tenant_id=existing.tenant_id,
            file_id=existing.file_id,
            status=status,
            message=updates.get("message", existing.message),
            output_gcs_uri=updates.get("output_gcs_uri", existing.output_gcs_uri),
            error_code=updates.get("error_code", existing.error_code),
            updated_at=datetime.now(timezone.utc),
        )

        await self.set_status(trace_id, updated)

    # Tenant configuration

    async def get_tenant_config(self, tenant_id: str) -> Optional[TenantConfig]:
        """Get tenant-specific configuration."""
        key = self._tenant_key(tenant_id)

        if not self._redis_available:
            data = self._memory_cache.get(key)
            return self._deserialize_tenant_config(data) if data else None

        def _get():
            try:
                data = self.client.get(key)
                return self._deserialize_tenant_config(data) if data else None
            except Exception as e:
                logger.error(f"Redis get_tenant_config error: {e}")
                raise CacheError(f"Failed to get tenant config: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get)

    async def set_tenant_config(
        self,
        tenant_id: str,
        config: TenantConfig,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store tenant configuration."""
        key = self._tenant_key(tenant_id)
        data = self._serialize_tenant_config(config)
        ttl = ttl_seconds or self.tenant_ttl

        if not self._redis_available:
            self._memory_cache[key] = data
            return

        def _set():
            try:
                self.client.setex(key, ttl, data)
            except Exception as e:
                logger.error(f"Redis set_tenant_config error: {e}")
                raise CacheError(f"Failed to set tenant config: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _set)

    # Deduplication

    async def is_duplicate(self, event_id: str) -> bool:
        """Check if event has already been processed."""
        key = self._dedupe_key(event_id)

        if not self._redis_available:
            return key in self._memory_cache

        def _check():
            try:
                return bool(self.client.exists(key))
            except Exception as e:
                logger.error(f"Redis is_duplicate error: {e}")
                raise CacheError(f"Failed to check duplicate: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)

    async def mark_processed(
        self,
        event_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Mark event as processed for deduplication."""
        key = self._dedupe_key(event_id)
        ttl = ttl_seconds or self.dedupe_ttl

        if not self._redis_available:
            self._memory_cache[key] = datetime.now(timezone.utc).isoformat()
            return

        def _mark():
            try:
                self.client.setex(key, ttl, datetime.now(timezone.utc).isoformat())
            except Exception as e:
                logger.error(f"Redis mark_processed error: {e}")
                raise CacheError(f"Failed to mark processed: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _mark)

    # Health check

    async def is_healthy(self) -> bool:
        """Check if cache service is available."""
        if not self._redis_available:
            return True  # In-memory mode is always "healthy"

        def _check():
            try:
                self.client.ping()
                return True
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)
