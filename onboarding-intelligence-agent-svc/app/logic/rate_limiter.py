"""Per-user rate limiting via Redis counters (M-05, §14).

One counter per tenant per user, shared by PREP turns and WS control frames.
The counter key is ``oia:v1:{tenant}:ratelimit:{user_id}`` with a 60-second
TTL set on the first increment — a simple sliding window.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

WINDOW_S = 60


async def check_rate(redis_client: Any, key: str, limit: int) -> tuple[int, bool]:
    """Increment the counter and return (count, exceeded).

    ``INCR`` is atomic across Cloud Run instances because it is a single Redis
    command. The ``EXPIRE`` on the first increment creates the 60-second
    window; subsequent increments do not reset the TTL.
    """
    count: int = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, WINDOW_S)
    exceeded = count > limit
    if exceeded:
        logger.warning(
            "rate_limit_exceeded",
            key=key,
            count=count,
            limit=limit,
        )
    return count, exceeded
