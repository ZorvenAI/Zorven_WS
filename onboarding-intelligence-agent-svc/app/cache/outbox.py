"""Backend write outbox — buffers writes while the circuit breaker is open.

Phase B, Gap 4 of the OIA resilience plan.

When the ``backend`` circuit breaker opens, writes (POST/PATCH) that would
otherwise be silently dropped are serialised to a per-tenant Redis list. When
the breaker recovers (transitions to CLOSED), a drain callback replays the
queued entries FIFO. Each tenant's queue is bounded; overflow drops the oldest
entry and emits a warning.

**Reads are not buffered.** A stale read cannot be replayed meaningfully —
the response is time-dependent — so ``_get`` still returns None when the
breaker is open.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from app.cache.redis_manager import BACKEND_OUTBOX_SCAN, TTL_OUTBOX, RedisManager
from app.circuit_breaker.breaker import CircuitBreaker, State
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_ENTRIES_DEFAULT = 200


class OutboxWriter:
    """Buffers backend writes in Redis for replay on breaker recovery."""

    def __init__(
        self,
        redis: RedisManager,
        *,
        max_entries: int = MAX_ENTRIES_DEFAULT,
        on_overflow: Callable[[str, int], Awaitable[None]] | None = None,
    ) -> None:
        self._redis = redis
        self._max_entries = max_entries
        self._draining = False
        self._on_overflow = on_overflow

    async def enqueue(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any],
        tenant_id: str,
        timeout: float = 5.0,
    ) -> None:
        """Append a write to the tenant's outbox list.

        Bounded at ``max_entries``. When the list exceeds the bound, the
        oldest entries are trimmed atomically via LTRIM.
        """
        keys = self._redis.keys_for(tenant_id)
        key = keys.backend_outbox()
        entry = json.dumps(
            {
                "method": method,
                "path": path,
                "payload": payload,
                "tenant_id": tenant_id,
                "timeout": timeout,
                "enqueued_at": time.time(),
            }
        )

        pipe = self._redis.client.pipeline()
        pipe.rpush(key, entry)
        pipe.ltrim(key, -self._max_entries, -1)
        pipe.expire(key, TTL_OUTBOX)
        results = await pipe.execute()
        length: int = results[0]

        if length > self._max_entries:
            excess = length - self._max_entries
            logger.warning(
                "outbox_overflow",
                tenant=tenant_id,
                dropped=excess,
                bound=self._max_entries,
            )
            if self._on_overflow is not None:
                try:
                    await self._on_overflow(tenant_id, excess)
                except Exception:
                    pass

        logger.info(
            "outbox_enqueued",
            tenant=tenant_id,
            method=method,
            path=path,
            queue_depth=min(length, self._max_entries),
        )

    async def drain_all(
        self,
        replay_fn: Callable[[dict[str, Any]], Awaitable[bool]],
    ) -> int:
        """Scan all tenants and replay buffered writes via ``replay_fn``.

        ``replay_fn`` receives a dict with keys ``method``, ``path``,
        ``payload``, ``tenant_id``, ``timeout`` and returns True on success,
        False on failure (which stops the drain for that tenant but continues
        to the next).

        Returns the total number of entries successfully replayed.
        """
        if self._draining:
            logger.info("outbox_drain_already_running")
            return 0
        self._draining = True
        try:
            return await self._drain_impl(replay_fn)
        finally:
            self._draining = False

    async def _drain_impl(
        self,
        replay_fn: Callable[[dict[str, Any]], Awaitable[bool]],
    ) -> int:
        pattern = BACKEND_OUTBOX_SCAN
        total = 0
        cursor: int = 0

        while True:
            cursor, found_keys = await self._redis.client.scan(
                cursor=cursor, match=pattern, count=100
            )
            for key in found_keys:
                key_str = key if isinstance(key, str) else key.decode()
                count, failed = await self._drain_key(key_str, replay_fn)
                total += count
                if failed:
                    logger.info(
                        "outbox_drain_tenant_stopped",
                        key=key_str,
                        reason="replay_failed",
                        tenant_drained=count,
                    )
            if cursor == 0:
                break

        if total:
            logger.info("outbox_drain_complete", total=total)
        return total

    async def _drain_key(
        self,
        key: str,
        replay_fn: Callable[[dict[str, Any]], Awaitable[bool]],
    ) -> tuple[int, bool]:
        """Drain one tenant's outbox. Returns (count_drained, hit_failure)."""
        drained = 0
        while True:
            raw: bytes | str | None = await cast(Any, self._redis.client.lpop(key))
            if raw is None:
                break
            if isinstance(raw, bytes):
                raw = raw.decode()
            try:
                entry: dict[str, Any] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning("outbox_corrupt_entry", key=key)
                continue

            try:
                ok = await replay_fn(entry)
            except Exception:
                ok = False

            if ok:
                drained += 1
                logger.info(
                    "outbox_replayed",
                    method=entry.get("method"),
                    path=entry.get("path"),
                    tenant=entry.get("tenant_id"),
                )
            else:
                pipe = self._redis.client.pipeline()
                pipe.lpush(key, raw)
                pipe.expire(key, TTL_OUTBOX)
                await pipe.execute()
                return drained, True
        return drained, False

    async def pending_count(self) -> int:
        """Total entries across all tenants (for monitoring)."""
        pattern = BACKEND_OUTBOX_SCAN
        total = 0
        cursor: int = 0
        while True:
            cursor, found_keys = await self._redis.client.scan(
                cursor=cursor, match=pattern, count=100
            )
            for key in found_keys:
                total += await cast(Any, self._redis.client.llen(key))
            if cursor == 0:
                break
        return total


def register_outbox_drain(
    breaker: CircuitBreaker,
    outbox: OutboxWriter,
    replay_fn: Callable[[dict[str, Any]], Awaitable[bool]],
) -> None:
    """Wire the backend breaker's recovery to drain the outbox."""

    async def _safe_drain() -> None:
        try:
            await outbox.drain_all(replay_fn)
        except Exception:
            logger.exception("outbox_drain_failed")

    def _on_backend_recovered(dep: str, old: State, new: State) -> None:
        if new != State.CLOSED:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("outbox_drain_no_loop")
            return
        loop.create_task(_safe_drain())

    breaker.add_on_state_change(_on_backend_recovered)
