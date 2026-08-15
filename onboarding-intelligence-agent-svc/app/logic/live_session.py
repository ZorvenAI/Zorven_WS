"""LiveSessionManager — seq, the replay buffer, and resume (F-04 PR 2).

Design §4.3, §9.2, §10.2.3 · AC-3 and AC-4.

Both pieces of state live in Redis and neither can live in the process. Spike
A-02 finding 3: sockets for one tenant land on different Cloud Run instances,
so a reconnect usually arrives somewhere that never saw the frames it is asking
to replay, and a counter held in memory would restart from one.

The speaker-turn batcher the scaffold's docstring also mentions is G-02's — it
batches *analysis*, not frames, and nothing here needs it to deliver a socket
that survives a reconnect.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.api.schemas import Resync, ServerFrame
from app.cache.redis_manager import TTL_LIVE

logger = logging.getLogger(__name__)

#: How many frames a reconnect can replay.
#:
#: A count, not a byte budget: AC-3 is about how far back a client can resume,
#: and "the last N frames" is a window an operator can reason about. At the
#: rates §2.1 implies — partials a few times a second — 2000 frames is several
#: minutes of meeting, comfortably past the reconnect A-02 measured.
#:
#: Capped at all because this is a shared Redis: an untrimmed list evicts
#: another service's data, which the eviction note in this service's CLAUDE.md
#: makes non-negotiable.
BUFFER_FRAMES = 2000


@dataclass
class LiveSessionManager:
    """One live session's frame state.

    Constructed per socket, but holds nothing durable itself — every read and
    write goes to Redis, so a second instance on another Cloud Run pod sees
    the same session.
    """

    redis: Any
    tenant_id: str
    session_id: str

    def _keys(self) -> Any:
        return self.redis.keys_for(self.tenant_id)

    async def next_seq(self) -> int:
        """The next number in the series (AC-4).

        `INCR` because it must be atomic. Two frames produced concurrently —
        a transcript partial and a coverage update, which is the ordinary case
        — would otherwise read the same value and both claim it, and "strictly
        increasing" would be false in exactly the situation that makes it
        matter.

        Starts at 1: seq 0 is what a client sends in `resume` before it has
        ever received anything, and a frame numbered 0 would be
        indistinguishable from that.
        """
        keys = self._keys()
        key = keys.live_seq(self.session_id)
        value = await self.redis.client.incr(key)
        await self.redis.client.expire(key, TTL_LIVE)
        return int(value)

    async def emit(self, frame: ServerFrame) -> dict[str, Any]:
        """Record a frame in the replay buffer and return it as JSON.

        Buffered *before* it is sent, not after. A frame delivered and not
        recorded is one a reconnect cannot replay, and the client would resume
        from a seq the server has no memory of.
        """
        payload = frame.model_dump(mode="json")
        keys = self._keys()
        key = keys.live_frames(self.session_id)

        await self.redis.client.rpush(key, json.dumps(payload))
        # Trim to the newest BUFFER_FRAMES. ltrim with negative indices keeps
        # the tail, which is the end a resume reads from.
        await self.redis.client.ltrim(key, -BUFFER_FRAMES, -1)
        await self.redis.client.expire(key, TTL_LIVE)
        return payload

    async def replay_after(
        self, last_seq: int
    ) -> tuple[list[dict[str, Any]], Resync | None]:
        """Frames after `last_seq`, or a resync if they are gone (AC-3).

        Returns ``(frames, None)`` when the window covers the request, and
        ``([], Resync)`` when it does not. AC-3 is explicit that the second
        case is answered "with an explicit resync frame, not a silent gap in
        seq" — a client that receives nothing cannot tell "you missed nothing"
        from "we no longer have what you missed", and renders a meeting with a
        hole in it either way.
        """
        keys = self._keys()
        raw = await self.redis.client.lrange(keys.live_frames(self.session_id), 0, -1)

        frames: list[dict[str, Any]] = []
        for item in raw:
            try:
                frames.append(json.loads(item))
            except (TypeError, ValueError):
                # A malformed entry is skipped rather than fatal: one bad frame
                # must not cost the client every good one after it.
                logger.warning(
                    "live_frame_unreadable", extra={"session": self.session_id}
                )

        if not frames:
            # Nothing buffered. Only a resync is honest — the server cannot
            # say whether the client is up to date.
            return [], Resync(seq=await self.next_seq(), from_seq=last_seq)

        oldest = min(int(f.get("seq", 0)) for f in frames)
        newest = max(int(f.get("seq", 0)) for f in frames)

        if last_seq + 1 < oldest:
            # The client's next frame has already been trimmed away.
            return [], Resync(seq=await self.next_seq(), from_seq=oldest)

        if last_seq > newest:
            # The client claims a seq the server never produced — the counter
            # was reset, the session was confused, or the keys collided across
            # tests. An empty "nothing to replay" would be indistinguishable
            # from "you are up to date" on the client side.
            return [], Resync(seq=await self.next_seq(), from_seq=oldest)

        return [f for f in frames if int(f.get("seq", 0)) > last_seq], None
