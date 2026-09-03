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

_LUA_INCR_WITH_EXPIRE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


async def check_rate(redis_client: Any, key: str, limit: int) -> tuple[int, bool]:
    """Increment the counter and return (count, exceeded).

    Uses a Lua script so the ``INCR`` and ``EXPIRE`` execute atomically in
    a single round trip. Without this, a crash between the two commands
    would leave a counter with no TTL — permanently rate-limiting the user.
    """
    count: int = await redis_client.eval(_LUA_INCR_WITH_EXPIRE, 1, key, WINDOW_S)
    exceeded = count > limit
    if exceeded:
        logger.warning(
            "rate_limit_exceeded",
            key=key,
            count=count,
            limit=limit,
        )
    return count, exceeded
