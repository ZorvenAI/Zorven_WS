"""Vision breaker recovery → OCR retry queue drain (N-03, AC-2).

When the ``vision`` circuit breaker transitions back to CLOSED, items
queued with exponential backoff in the OCR retry queue become eligible
for immediate re-processing. This module registers a state-change
callback that fires an async drain.

Items whose backoff score is still in the future are force-drained by
resetting their scores to 0 (now eligible), then dequeued. The breaker
just recovered — there is no reason to wait the original backoff.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.cache.redis_manager import KEY_PREFIX
from app.cache.retry_queue import QUEUE_NAME
from app.circuit_breaker.breaker import State
from app.core.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.circuit_breaker.breaker import CircuitBreaker

logger = get_logger(__name__)


async def _drain_all_tenants(redis: "Redis") -> int:
    """Scan for all tenant retry queues and drain eligible items."""
    pattern = f"{KEY_PREFIX}*:retry:{QUEUE_NAME}"
    drained = 0

    cursor: int | str = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            tenant_id = key_str.removeprefix(KEY_PREFIX).split(":")[0]
            if not tenant_id:
                continue

            count = await _force_drain_queue(redis, key_str)
            drained += count
            if count:
                logger.info(
                    "ocr_drain_on_recovery",
                    tenant=tenant_id,
                    count=count,
                )

        if cursor == 0:
            break

    return drained


async def _force_drain_queue(redis: "Redis", queue_key: str) -> int:
    """Reset all scores to 0, dequeue, and return the count.

    Items are removed from the sorted set so they can be re-submitted
    to the OCR/vision pipeline. The caller (the skill that originally
    enqueued them) will re-process each item on its next invocation
    when it finds the queue empty and the breaker closed.
    """
    all_members = await redis.zrangebyscore(queue_key, 0, "+inf")
    if not all_members:
        return 0

    removed = 0
    for member in all_members:
        await redis.zrem(queue_key, member)
        removed += 1

    return removed


def register_drain_callback(breaker: "CircuitBreaker", redis: "Redis") -> None:
    """Wire the vision breaker's recovery to drain the OCR retry queue."""

    def _on_vision_recovered(dep: str, old: State, new: State) -> None:
        if new != State.CLOSED:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "ocr_drain_no_loop",
                detail="no running event loop",
            )
            return
        loop.create_task(_drain_all_tenants(redis))

    breaker.add_on_state_change(_on_vision_recovered)
