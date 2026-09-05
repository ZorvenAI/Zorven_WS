"""Vision breaker recovery → OCR retry queue drain (N-03, AC-2).

When the ``vision`` circuit breaker transitions back to CLOSED, items
queued with exponential backoff in the OCR retry queue become eligible
for immediate re-processing. This module registers a state-change
callback that fires an async drain.

Items whose backoff score is still in the future are left alone —
:func:`~app.cache.retry_queue.dequeue_due` respects the score.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.cache.redis_manager import KEY_PREFIX
from app.cache.retry_queue import QUEUE_NAME, dequeue_due
from app.circuit_breaker.breaker import State

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.circuit_breaker.breaker import CircuitBreaker

logger = logging.getLogger(__name__)


async def _drain_all_tenants(redis: "Redis") -> int:
    """Scan for all tenant retry queues and drain due items."""
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

            from app.cache.redis_manager import TenantKeys as _TK

            items = await dequeue_due(redis, _TK(tenant_id))
            drained += len(items)
            if items:
                logger.info(
                    "ocr_drain_on_recovery",
                    tenant=tenant_id,
                    count=len(items),
                )

        if cursor == 0:
            break

    return drained


def register_drain_callback(breaker: "CircuitBreaker", redis: "Redis") -> None:
    """Wire the vision breaker's recovery to drain the OCR retry queue."""

    def _on_vision_recovered(dep: str, old: State, new: State) -> None:
        if new != State.CLOSED:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("ocr_drain_no_loop", detail="no running event loop")
            return
        loop.create_task(_drain_all_tenants(redis))

    breaker.add_on_state_change(_on_vision_recovered)
