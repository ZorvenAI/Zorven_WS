"""One live socket at a time (F-04 AC-2).

The lock lives in Redis because it has to. Spike A-02, finding 3: sockets for
one tenant land on different Cloud Run instances, so a process-local flag would
admit one socket per instance and call it exclusivity.

**Keyed on company, not session.** AC-2 says "one live socket per session";
`TenantKeys.live_lock` is keyed on company and gives its reason: "keying it on
the session would make the lock trivially satisfiable by opening a second
session." The two agree in practice — B-01 permits one non-terminal session per
company — and where they differ, the company key is the stricter of the two. A
second socket for the same session contends for the same key either way, which
is what AC-2 actually asks for.

The TTL is what makes a crash survivable. Holding a lock with no expiry means a
process that dies mid-meeting locks that company out until somebody notices,
and the operator's remedy is a support ticket.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Shorter than the two hours TenantKeys documents for a live lock.
#:
#: The lock is refreshed while the socket is alive, so its expiry only matters
#: after a crash — and it is how long the company waits before they can start
#: again. Two hours is a meeting; ninety seconds is an apology.
LOCK_TTL_S = 90

#: How often a live socket extends its own claim. Comfortably inside the TTL,
#: so a slow tick does not drop a lock out from under a healthy meeting.
REFRESH_S = 30


@dataclass
class LiveLock:
    """A claim on one company's live slot, held for the life of a socket."""

    key: str
    token: str
    _client: object | None = None

    async def refresh(self) -> bool:
        """Extend the claim. False means we no longer hold it.

        Checked rather than assumed: if the TTL lapsed and another socket took
        the slot, blindly re-setting the key would give two sockets the same
        lock and silently break the guarantee.
        """
        client = self._client
        if client is None:
            return False
        current = await client.get(self.key)  # type: ignore[attr-defined]
        if _as_text(current) != self.token:
            return False
        await client.expire(self.key, LOCK_TTL_S)  # type: ignore[attr-defined]
        return True

    async def release(self) -> None:
        """Give the slot back, but only if it is still ours.

        A socket that stalled past its TTL may find another has taken over;
        deleting the key then would evict a live meeting to tidy up after a
        dead one.
        """
        client = self._client
        if client is None:
            return
        current = await client.get(self.key)  # type: ignore[attr-defined]
        if _as_text(current) == self.token:
            await client.delete(self.key)  # type: ignore[attr-defined]


def _as_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return "" if value is None else str(value)


async def acquire(
    redis_manager: Any,
    *,
    tenant_id: str,
    company_id: str,
    token: str,
    max_slots: int = 1,
) -> LiveLock | None:
    """Claim a live slot, or return None if all slots are taken.

    ``SET key token NX EX ttl`` — one round trip, and atomic. A get-then-set
    would let two handshakes arriving together both find the key empty and
    both proceed, which is precisely the race AC-2 is about and precisely the
    one that never shows up in a single-threaded test.

    When ``max_slots > 1`` (tenant-configurable per M-05 AC-2), the function
    tries each slot sequentially. Slot 0 is backward-compatible with the
    original single-slot key.
    """
    if redis_manager is None or not company_id:
        return None

    keys = redis_manager.keys_for(tenant_id)
    client = redis_manager.client

    for slot in range(max(1, max_slots)):
        key = keys.live_lock_slot(company_id, slot)
        acquired = await client.set(key, token, nx=True, ex=LOCK_TTL_S)
        if acquired:
            return LiveLock(key=key, token=token, _client=client)

    logger.info(
        "live_lock_contended",
        extra={"tenant_id": tenant_id, "slots": max_slots},
    )
    return None
