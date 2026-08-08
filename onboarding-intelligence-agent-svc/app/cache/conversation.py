"""Prep conversation state, keyed on the chat session (C-01 AC-2).

An operator prepares over several turns and refers back — "make the third
question deeper" — so the agent needs what was said earlier. That history
lives in Redis DB 2 under ``oia:v1:{tenant}:chat:{chat_session_id}``, per
ERRATA-01 rather than §14's DB 27.

**This story stores and returns the history; it does not resolve references
against it.** Resolving "the third question" needs a questionnaire and a skill
to reason over one, which are C-02 and C-03. Delivering the mechanism and
saying so is more useful than a half-built resolver that appears to work.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable
from typing import Any, cast

from app.cache.redis_manager import TTL_CHAT, RedisManager

logger = logging.getLogger(__name__)

#: How many turns to keep. A prep conversation that ran past this has more
#: context than a prompt window can use anyway, and an unbounded list on a
#: shared Redis is the other half of the leak the TTL guards against.
MAX_TURNS = 40


class ConversationStore:
    """Append-and-read the turns of one prep conversation.

    Every method takes the tenant, and the key is built through ``TenantKeys``
    — obtained from ``RedisManager.keys_for`` — so a tenant-less key cannot be
    constructed. That is A-03's rule: "a helper that can be called without a
    tenant will eventually be called without one."
    """

    def __init__(self, redis_manager: "RedisManager") -> None:
        self._redis = redis_manager

    def _key(self, tenant_id: str, chat_session_id: str) -> str:
        key: str = self._redis.keys_for(tenant_id).chat(chat_session_id)
        return key

    async def append(
        self, *, tenant_id: str, chat_session_id: str, role: str, text: str
    ) -> None:
        """Record one turn and refresh the sliding TTL.

        The TTL is re-applied on every write rather than only on the first, so
        an active conversation survives and an abandoned one expires — which
        is what "sliding" means and what stops a busy tenant's keys from
        vanishing mid-preparation.
        """
        key = self._key(tenant_id, chat_session_id)
        turn = json.dumps({"role": role, "text": text}, separators=(",", ":"))

        client = self._redis.client
        pipe = client.pipeline()
        pipe.rpush(key, turn)
        pipe.ltrim(key, -MAX_TURNS, -1)
        pipe.expire(key, TTL_CHAT)
        await pipe.execute()

    async def history(
        self, *, tenant_id: str, chat_session_id: str
    ) -> list[dict[str, Any]]:
        """Every retained turn, oldest first.

        A malformed entry is skipped rather than raising: one unparseable turn
        should cost that turn, not the whole conversation the operator is in
        the middle of.
        """
        key = self._key(tenant_id, chat_session_id)
        # redis-py types lrange as Awaitable[list] | list, because the same
        # signature serves the sync and async clients. This is always the
        # async one, so the call is cast before it is awaited — casting the
        # result instead leaves mypy awaiting a union.
        raw = await cast("Awaitable[list[Any]]", self._redis.client.lrange(key, 0, -1))

        turns: list[dict[str, Any]] = []
        for entry in raw:
            try:
                turns.append(json.loads(entry))
            except (TypeError, ValueError):
                logger.warning("dropping an unparseable turn from %s", key)
        return turns

    async def clear(self, *, tenant_id: str, chat_session_id: str) -> None:
        await self._redis.client.delete(self._key(tenant_id, chat_session_id))
