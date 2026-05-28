"""Re-optimization debounce manager (§14.2).

Coalesces multiple campaign completions within a 24-hour window
into a single re-optimization run per tenant+agent.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

DEBOUNCE_KEY_TEMPLATE = "reopt:debounce:{tenant_id}:{agent_code}"
DEBOUNCE_TTL_SECONDS = settings.REOPT_DEBOUNCE_HOURS * 3600


async def is_debounced(prompt_cache, tenant_id: str, agent_code: str) -> bool:
    """Check if a re-optimization trigger is within the debounce window.

    Returns True if a trigger was already processed within the window.
    """
    r = await prompt_cache.connect()
    key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
    return await r.exists(key) > 0


async def set_debounce(prompt_cache, tenant_id: str, agent_code: str) -> None:
    """Set the debounce key with TTL to prevent duplicate triggers."""
    r = await prompt_cache.connect()
    key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
    await r.set(key, "1", ex=DEBOUNCE_TTL_SECONDS)
    logger.debug("Debounce set: %s (TTL %ds)", key, DEBOUNCE_TTL_SECONDS)


async def clear_debounce(prompt_cache, tenant_id: str, agent_code: str) -> None:
    """Clear the debounce key (for testing or manual reset)."""
    r = await prompt_cache.connect()
    key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
    await r.delete(key)
