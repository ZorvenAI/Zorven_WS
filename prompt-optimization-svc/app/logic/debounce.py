"""Re-optimization debounce manager (§14.2).

Coalesces multiple campaign completions within a 24-hour window
into a single re-optimization run per tenant+agent.
Uses atomic SET NX EX for race-safe debouncing.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

DEBOUNCE_KEY_TEMPLATE = "reopt:debounce:{tenant_id}:{agent_code}"
DEBOUNCE_TTL_SECONDS = settings.REOPT_DEBOUNCE_HOURS * 3600


async def try_acquire_debounce(prompt_cache, tenant_id: str, agent_code: str) -> bool:
    """Atomically check-and-set the debounce key.

    Uses SET NX EX for race-safe coalescing across multiple instances.

    Returns True if the debounce was acquired (first trigger).
    Returns False if already debounced (duplicate trigger).
    """
    r = await prompt_cache.connect()
    key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
    # SET key "1" NX EX ttl — returns True if set, None if already exists
    acquired = await r.set(key, "1", nx=True, ex=DEBOUNCE_TTL_SECONDS)
    if acquired:
        logger.debug("Debounce acquired: %s (TTL %ds)", key, DEBOUNCE_TTL_SECONDS)
    return bool(acquired)


async def is_debounced(prompt_cache, tenant_id: str, agent_code: str) -> bool:
    """Check if a re-optimization trigger is within the debounce window."""
    r = await prompt_cache.connect()
    key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
    return await r.exists(key) > 0


async def clear_debounce(prompt_cache, tenant_id: str, agent_code: str) -> None:
    """Clear the debounce key (for testing or manual reset)."""
    r = await prompt_cache.connect()
    key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
    await r.delete(key)
