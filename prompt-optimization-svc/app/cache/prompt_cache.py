"""Prompt cache manager — Redis DB 2 for prompt storage, locks, and progress.

Key naming convention (§9.1):
  prompt:<name>:production               — global production prompt
  prompt:<name>:tenant:<tid>             — tenant-specific override
  prompt:optimization:lock:<group>       — distributed optimization lock
  prompt:optimization:progress:<run_id>  — optimization run progress hash
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL defaults (seconds)
DEFAULT_PROMPT_TTL = 300  # 5 minutes
LOCK_TTL = 7200  # 2 hours
PROGRESS_TTL = 86400  # 24 hours


class PromptCacheManager:
    """Redis DB 2 — prompt cache, optimization locks, and progress tracking."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> aioredis.Redis:
        """Initialize and return the Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url, decode_responses=True
            )
        return self._redis

    @property
    def client(self) -> Optional[aioredis.Redis]:
        """Return the raw Redis client (for health checks)."""
        return self._redis

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ------------------------------------------------------------------
    # Prompt cache (AC-1)
    # ------------------------------------------------------------------

    @staticmethod
    def _prompt_key(name: str, tenant_id: Optional[str] = None) -> str:
        """Build the Redis key for a prompt.

        Returns:
            prompt:<name>:tenant:<tid>  if tenant_id is set
            prompt:<name>:production    otherwise
        """
        if tenant_id:
            return f"prompt:{name}:tenant:{tenant_id}"
        return f"prompt:{name}:production"

    async def get_prompt(
        self, name: str, tenant_id: Optional[str] = None
    ) -> Optional[str]:
        """Get a cached prompt template. Returns None on miss or error."""
        try:
            r = await self.connect()
            key = self._prompt_key(name, tenant_id)
            return await r.get(key)
        except Exception as exc:
            logger.warning("Prompt cache get error: %s", exc)
            return None

    async def set_prompt(
        self,
        name: str,
        template: str,
        ttl: int = DEFAULT_PROMPT_TTL,
        tenant_id: Optional[str] = None,
    ) -> None:
        """Cache a prompt template with TTL."""
        try:
            r = await self.connect()
            key = self._prompt_key(name, tenant_id)
            await r.set(key, template, ex=ttl)
            logger.debug("Prompt cached: %s (ttl=%ds)", key, ttl)
        except Exception as exc:
            logger.warning("Prompt cache set error: %s", exc)

    async def invalidate_prompt(self, name: str) -> int:
        """Delete all cached versions of a prompt (production + tenant overrides).

        Returns the number of keys deleted.
        """
        try:
            r = await self.connect()
            keys = []
            async for key in r.scan_iter(match=f"prompt:{name}:*"):
                keys.append(key)
            if keys:
                deleted = await r.delete(*keys)
                logger.info("Prompt invalidated: %s (%d keys)", name, deleted)
                return deleted
            return 0
        except Exception as exc:
            logger.warning("Prompt cache invalidate error: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Optimization lock (AC-2)
    # ------------------------------------------------------------------

    @staticmethod
    def _lock_key(group: str) -> str:
        """Build the Redis key for an optimization lock."""
        return f"prompt:optimization:lock:{group}"

    async def acquire_optimization_lock(
        self, group: str, owner: str, ttl: int = LOCK_TTL
    ) -> bool:
        """Acquire a distributed optimization lock.

        Uses SET NX EX for atomic acquire with 2-hour TTL.
        Returns True if lock was acquired, False if already held.
        """
        try:
            r = await self.connect()
            key = self._lock_key(group)
            acquired = await r.set(key, owner, nx=True, ex=ttl)
            if acquired:
                logger.info("Lock acquired: %s (owner=%s, ttl=%ds)", group, owner, ttl)
            else:
                logger.debug("Lock not acquired: %s (already held)", group)
            return bool(acquired)
        except Exception as exc:
            logger.warning("Lock acquire error: %s", exc)
            return False

    # Lua script for atomic compare-and-delete (lock release)
    _RELEASE_LOCK_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """

    async def release_optimization_lock(
        self, group: str, owner: str
    ) -> bool:
        """Release an optimization lock (only if held by the given owner).

        Uses an atomic Lua script to compare-and-delete, preventing race
        conditions where the lock expires and is re-acquired between
        GET and DEL.

        Returns True if released, False if not held or held by another owner.
        """
        try:
            r = await self.connect()
            key = self._lock_key(group)
            result = await r.eval(self._RELEASE_LOCK_SCRIPT, 1, key, owner)
            if result:
                logger.info("Lock released: %s (owner=%s)", group, owner)
                return True
            logger.debug("Lock release denied: %s (owner=%s)", group, owner)
            return False
        except Exception as exc:
            logger.warning("Lock release error: %s", exc)
            return False

    async def get_optimization_lock_info(
        self, group: str
    ) -> Optional[dict[str, Any]]:
        """Get lock info (owner and remaining TTL)."""
        try:
            r = await self.connect()
            key = self._lock_key(group)
            owner = await r.get(key)
            if owner is None:
                return None
            ttl = await r.ttl(key)
            return {"group": group, "owner": owner, "ttl_seconds": ttl}
        except Exception as exc:
            logger.warning("Lock info error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Optimization progress (AC-3)
    # ------------------------------------------------------------------

    @staticmethod
    def _progress_key(run_id: str) -> str:
        """Build the Redis key for optimization progress."""
        return f"prompt:optimization:progress:{run_id}"

    async def set_optimization_progress(
        self,
        run_id: str,
        progress: dict[str, Any],
        ttl: int = PROGRESS_TTL,
    ) -> None:
        """Set optimization progress as a Redis hash with 24-hour TTL."""
        try:
            r = await self.connect()
            key = self._progress_key(run_id)
            # Serialize complex values to JSON strings for Redis hash
            flat = {
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in progress.items()
            }
            flat["updated_at"] = datetime.now(timezone.utc).isoformat()
            await r.hset(key, mapping=flat)
            await r.expire(key, ttl)
            logger.debug("Progress updated: %s", run_id)
        except Exception as exc:
            logger.warning("Progress set error: %s", exc)

    async def get_optimization_progress(
        self, run_id: str
    ) -> Optional[dict[str, str]]:
        """Get optimization progress hash. Returns None if not found."""
        try:
            r = await self.connect()
            key = self._progress_key(run_id)
            data = await r.hgetall(key)
            return data if data else None
        except Exception as exc:
            logger.warning("Progress get error: %s", exc)
            return None

    async def delete_optimization_progress(self, run_id: str) -> None:
        """Delete optimization progress hash."""
        try:
            r = await self.connect()
            key = self._progress_key(run_id)
            await r.delete(key)
            logger.debug("Progress deleted: %s", run_id)
        except Exception as exc:
            logger.warning("Progress delete error: %s", exc)
