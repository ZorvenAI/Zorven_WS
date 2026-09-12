"""Write deduplication for retried dispatches.

Design §18.1 · implemented by B-06 (Gap 5).

Wraps the check/store pattern used by ``ProcessExecutor`` for idempotency
keys and job state.  Both share the same Redis key namespace
(``TenantKeys.idempotency``) and the same GET → JSON-parse / SET → JSON-dump
cycle; this class owns that cycle so every caller gets consistent TTL
enforcement and corrupt-data handling.
"""

from __future__ import annotations

import json
from typing import Any

from app.cache.redis_manager import RedisManager, TTL_IDEMPOTENCY


class IdempotencyGuard:
    """Check-or-store deduplication backed by Redis.

    The PROCESS key is sha256(session_id + evidence_manifest_hash): re-running
    over unchanged evidence returns the original job_id and writes nothing
    twice, while genuinely changed evidence produces a new hash and a real
    re-run.

    Parameters
    ----------
    redis : RedisManager
        The shared Redis manager (DB 2, ``oia:v1:`` prefix).
    """

    def __init__(self, redis: RedisManager) -> None:
        self._redis = redis

    async def check(self, tenant_id: str, digest: str) -> dict[str, Any] | None:
        """Return the cached payload for *digest*, or ``None``.

        Corrupt JSON is treated as a miss — the caller will overwrite it on
        the next store.
        """
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(digest)
        raw = await self._redis.client.get(key)
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(parsed, dict):
            return None
        return parsed

    async def store(
        self,
        tenant_id: str,
        digest: str,
        payload: dict[str, Any],
        ttl: int = TTL_IDEMPOTENCY,
    ) -> None:
        """Persist *payload* under *digest* with the given TTL."""
        keys = self._redis.keys_for(tenant_id)
        key = keys.idempotency(digest)
        await self._redis.client.set(key, json.dumps(payload), ex=ttl)
