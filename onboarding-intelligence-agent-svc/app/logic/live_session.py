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
from dataclasses import dataclass
from typing import Any

from app.api.schemas import Resync, ServerFrame
from app.cache.redis_manager import TTL_LIVE
from app.core.logging import get_logger

logger = get_logger(__name__)

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


def _parse_seq(raw: str | bytes | None) -> int | None:
    """Extract the seq from a single raw Redis entry.

    Returns ``None`` for anything unparseable rather than a sentinel like 0,
    which would defeat the resync guard.
    """
    if raw is None:
        return None
    try:
        frame = json.loads(raw)
        if not isinstance(frame, dict):
            return None
        seq = frame.get("seq")
        return int(seq) if isinstance(seq, int) and seq > 0 else None
    except (TypeError, ValueError):
        return None


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

        Pipelined with EXPIRE so a crash between the two cannot orphan a
        TTL-less key on the shared noeviction Redis.

        Starts at 1: seq 0 is what a client sends in `resume` before it has
        ever received anything, and a frame numbered 0 would be
        indistinguishable from that.
        """
        keys = self._keys()
        key = keys.live_seq(self.session_id)
        pipe = self.redis.client.pipeline(transaction=False)
        pipe.incr(key)
        pipe.expire(key, TTL_LIVE)
        results = await pipe.execute()
        return int(results[0])

    async def _peek_seq(self) -> int:
        """Read the counter without advancing it."""
        key = self._keys().live_seq(self.session_id)
        val = await self.redis.client.get(key)
        return int(val) if val else 0

    async def emit(self, frame: ServerFrame) -> dict[str, Any]:
        """Record a frame in the replay buffer and return it as JSON.

        Buffered *before* it is sent, not after. A frame delivered and not
        recorded is one a reconnect cannot replay, and the client would resume
        from a seq the server has no memory of.

        All three operations (rpush, ltrim, expire) are pipelined into a single
        round-trip. Separate awaits would let a crash between rpush and expire
        orphan a TTL-less key on the shared noeviction Redis.
        """
        payload = frame.model_dump(mode="json")
        keys = self._keys()
        key = keys.live_frames(self.session_id)

        pipe = self.redis.client.pipeline(transaction=False)
        pipe.rpush(key, json.dumps(payload))
        pipe.ltrim(key, -BUFFER_FRAMES, -1)
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()
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

        Bounds are checked via LLEN + LINDEX in a single pipeline round-trip
        before any frames are read, so a resync or an up-to-date client never
        transfers the full buffer. The replay tail is sorted by seq to handle
        the rare case where concurrent emit() calls interleave their rpush
        operations.
        """
        keys = self._keys()
        key = keys.live_frames(self.session_id)

        pipe = self.redis.client.pipeline(transaction=False)
        pipe.llen(key)
        pipe.lindex(key, 0)
        pipe.lindex(key, -1)
        length, first_raw, last_raw = await pipe.execute()

        if not length:
            current = await self._peek_seq()
            return [], Resync(from_seq=current + 1)

        oldest = _parse_seq(first_raw)
        newest = _parse_seq(last_raw)

        if oldest is None or newest is None:
            raw = await self.redis.client.lrange(key, 0, -1)
            return self._filter_and_sort(raw, last_seq)

        if last_seq + 1 < oldest:
            return [], Resync(from_seq=oldest)

        if last_seq > newest:
            return [], Resync(from_seq=oldest)

        offset = max(0, last_seq - oldest + 1)
        raw = await self.redis.client.lrange(key, offset, -1)
        return self._filter_and_sort(raw, last_seq)

    def _filter_and_sort(
        self, raw: list[Any], last_seq: int
    ) -> tuple[list[dict[str, Any]], None]:
        """Parse, filter by seq, and sort the result."""
        frames: list[dict[str, Any]] = []
        for item in raw:
            try:
                frame = json.loads(item)
                seq = frame.get("seq")
                if isinstance(seq, int) and seq > 0 and seq > last_seq:
                    frames.append(frame)
            except (TypeError, ValueError):
                logger.warning("live_frame_unreadable", session=self.session_id)
        frames.sort(key=lambda f: f["seq"])
        return frames, None
