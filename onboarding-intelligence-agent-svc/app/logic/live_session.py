"""LiveSessionManager — seq, replay buffer, resume, session mode, and batcher.

Design §4.3, §9.2, §10.2.3 · AC-3 and AC-4 (F-04 PR 2).
Session mode and question marks added by F-06 (§18.2 degraded mode).
Speaker-turn batcher and question state added by G-02.
Version-based green signals added by G-03.

Both pieces of state live in Redis and neither can live in the process. Spike
A-02 finding 3: sockets for one tenant land on different Cloud Run instances,
so a reconnect usually arrives somewhere that never saw the frames it is asking
to replay, and a counter held in memory would restart from one.

The batcher is the one exception: it is in-process because it accumulates a few
seconds of segments between LLM calls, and losing that on a reconnect is
cheaper than a Redis round-trip per finalized segment. A reconnect replays
buffered frames and resumes batching from scratch.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from app.api.schemas import Resync, ServerFrame
from app.cache.redis_manager import TTL_LIVE
from app.core.logging import get_logger

logger = get_logger(__name__)

_ARRAY_FIELDS = ("evidence", "missing_aspects")


def _normalize_array_fields(entry: dict[str, Any]) -> None:
    """Lua cjson encodes empty arrays as {} — normalize back to []."""
    for field in _ARRAY_FIELDS:
        val = entry.get(field)
        if isinstance(val, dict) and not val:
            entry[field] = []


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


# ── Segment batcher (G-02, Design §4.3) ─────────────────────────────


@dataclass
class SegmentBatch:
    """A window of finalized segments ready for analysis."""

    segments: list[dict[str, Any]]
    recording_id: str
    first_t: float
    last_t: float


class SegmentBatcher:
    """Accumulates finalized segments and fires on speaker change or timer.

    Design §4.3: "analysis fires on a 3-second window or a speaker change,
    whichever comes first, so a short brand-owner answer is analysed as a
    unit rather than split across two calls."

    AC-1: "a 400-millisecond mid-sentence fragment is never dispatched to the
    model on its own."

    Plain Python, not async. One instance per live session, created in _hold().
    """

    def __init__(
        self,
        *,
        recording_id: str = "",
        window_s: float = 3.0,
        min_duration_s: float = 0.4,
    ) -> None:
        self._recording_id = recording_id
        self._window_s = window_s
        self._min_duration_s = min_duration_s
        self._pending: list[dict[str, Any]] = []
        self._first_added: float | None = None
        self._last_speaker: int | None = None

    @property
    def recording_id(self) -> str:
        return self._recording_id

    @recording_id.setter
    def recording_id(self, value: str) -> None:
        self._recording_id = value

    def add(self, segment: dict[str, Any]) -> SegmentBatch | None:
        """Add a finalized segment. Returns a batch when a trigger fires.

        Trigger conditions (whichever comes first):
        1. The speaker changed from the previous segment.
        2. Wall-clock time since the first segment in the batch >= window_s.

        A batch whose total audio duration < min_duration_s is held until the
        next segment joins it — never dispatched alone.
        """
        speaker = segment.get("speaker", 0)
        speaker_changed = (
            self._last_speaker is not None and speaker != self._last_speaker
        )

        batch: SegmentBatch | None = None
        if speaker_changed and self._pending:
            batch = self._try_fire()

        self._last_speaker = speaker
        self._pending.append(segment)
        if self._first_added is None:
            self._first_added = time.monotonic()

        if batch is not None:
            return batch

        elapsed = time.monotonic() - self._first_added
        if elapsed >= self._window_s:
            return self._try_fire()

        return None

    def check_timer(self) -> SegmentBatch | None:
        """Check whether the window timer has expired without a new segment.

        Called periodically from the event loop so a batch that filled early
        in the window is not held until the next segment arrives.
        """
        if not self._pending or self._first_added is None:
            return None
        if time.monotonic() - self._first_added >= self._window_s:
            return self._try_fire()
        return None

    def flush(self) -> SegmentBatch | None:
        """Force-fire whatever is accumulated (session end)."""
        if not self._pending:
            return None
        return self._build_batch()

    def _try_fire(self) -> SegmentBatch | None:
        """Fire if the batch meets the minimum duration threshold."""
        if not self._pending:
            return None
        first_t = self._pending[0].get("t_start", 0.0)
        last_t = self._pending[-1].get("t_end", 0.0)
        duration = last_t - first_t
        if duration < self._min_duration_s:
            return None
        return self._build_batch()

    def _build_batch(self) -> SegmentBatch:
        segments = list(self._pending)
        self._pending.clear()
        self._first_added = None
        first_t = segments[0].get("t_start", 0.0)
        last_t = segments[-1].get("t_end", 0.0)
        return SegmentBatch(
            segments=segments,
            recording_id=self._recording_id,
            first_t=first_t,
            last_t=last_t,
        )


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

    # ── Session mode (F-06) ─────────────────────────────────────────

    MODE_NORMAL = "NORMAL"
    MODE_RECORD_ONLY = "RECORD_ONLY"

    async def set_mode(self, mode: str) -> None:
        """Write the session mode to the Redis session hash."""
        keys = self._keys()
        key = keys.session(self.session_id)
        pipe = self.redis.client.pipeline(transaction=False)
        pipe.hset(key, "mode", mode)
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()

    async def get_mode(self) -> str:
        """Read the session mode; defaults to NORMAL if unset."""
        keys = self._keys()
        key = keys.session(self.session_id)
        val = await self.redis.client.hget(key, "mode")
        if val is None:
            return self.MODE_NORMAL
        return val if isinstance(val, str) else val.decode()

    # ── PII allowlist (G-01) ──────────────────────────────────────────

    async def set_allowlist(self, terms: list[str]) -> None:
        """Store company names that must not be redacted (AC-3)."""
        keys = self._keys()
        key = keys.session(self.session_id)
        pipe = self.redis.client.pipeline(transaction=False)
        pipe.hset(key, "allowlist", json.dumps(terms))
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()

    async def get_allowlist(self) -> list[str]:
        """Read the PII allowlist; empty if unset."""
        keys = self._keys()
        key = keys.session(self.session_id)
        raw = await self.redis.client.hget(key, "allowlist")
        if raw is None:
            return []
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else []
        except (TypeError, ValueError):
            return []

    # ── Manual question marks (F-06 minimal, G-03 extends) ──────────

    _LUA_MARK_QUESTION = """\
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then return 0 end
local entry = cjson.decode(raw)
local v = entry['version']
if v == nil then v = 0 end
entry['action'] = ARGV[2]
entry['source'] = 'manual'
entry['version'] = v + 1
if ARGV[2] == 'manual_ungreen' then
    entry['status'] = 'OPEN'
elseif ARGV[2] == 'manual_green' then
    entry['status'] = 'GREEN'
end
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(entry))
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
return v + 1
"""

    async def mark_question(self, question_id: str, action: str) -> int:
        """Store a manual checkmark, bumping version (AC-3).

        Returns the new version. A concurrent apply_green_signal reading an
        older version will fail its CAS check and be discarded — the ordering
        hazard from the G-03 tech notes.
        """
        keys = self._keys()
        key = keys.questions(self.session_id)
        result = await self.redis.client.eval(
            self._LUA_MARK_QUESTION,
            1,
            key,
            question_id,
            action,
            str(TTL_LIVE),
        )
        return int(result)

    async def get_question_marks(self) -> dict[str, Any]:
        """Read all question marks for this session."""
        keys = self._keys()
        key = keys.questions(self.session_id)
        raw = await self.redis.client.hgetall(key)
        result: dict[str, Any] = {}
        for k, v in raw.items():
            fld = k if isinstance(k, str) else k.decode()
            try:
                entry = json.loads(v)
                _normalize_array_fields(entry)
                result[fld] = entry
            except (TypeError, ValueError):
                pass
        return result

    # ── Approved questions (G-02) ──────────────────────────────────

    async def set_questions(self, questions: list[dict[str, Any]]) -> None:
        """Store the approved question list for analysis mapping.

        Called once during _hold() after a successful handshake. Each question
        is stored as a hash field keyed by its Django pk (as a string), so
        analysis results and manual marks write to the same namespace.
        """
        keys = self._keys()
        key = keys.questions(self.session_id)
        pipe = self.redis.client.pipeline(transaction=False)
        for q in questions:
            qid = str(q.get("id", ""))
            if not qid:
                continue
            entry = {
                "text": q.get("text", ""),
                "target_field": q.get("target_field", ""),
                "workflow_target": q.get("workflow_target", "WF1"),
                "status": q.get("status", "OPEN"),
                "evidence": [],
                "score": None,
                "source": "prepared",
                "version": 0,
                "missing_aspects": [],
            }
            pipe.hset(key, qid, json.dumps(entry))
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()

    async def get_questions(self) -> list[dict[str, Any]]:
        """Read the question list with current state for SKL-OIA-04."""
        keys = self._keys()
        key = keys.questions(self.session_id)
        raw = await self.redis.client.hgetall(key)
        result: list[dict[str, Any]] = []
        for k, v in raw.items():
            qid = k if isinstance(k, str) else k.decode()
            try:
                entry = json.loads(v)
                _normalize_array_fields(entry)
                entry["id"] = qid
                result.append(entry)
            except (TypeError, ValueError):
                pass
        result.sort(key=lambda q: q.get("text", ""))
        return result

    async def store_analysis_result(
        self,
        question_id: str,
        evidence: list[dict[str, Any]],
        relevance: float,
    ) -> None:
        """Update a question with evidence from analysis (G-02 AC-2)."""
        keys = self._keys()
        key = keys.questions(self.session_id)
        raw = await self.redis.client.hget(key, question_id)
        if raw is None:
            return
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            return
        existing = entry.get("evidence") or []
        existing.extend(evidence)
        entry["evidence"] = existing
        entry["source"] = "analysis"
        entry["relevance"] = relevance
        pipe = self.redis.client.pipeline(transaction=False)
        pipe.hset(key, question_id, json.dumps(entry))
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()

    # ── Green signals (G-03) ──────────────────────────────────────────

    _LUA_APPLY_GREEN = """\
local raw = redis.call('HGET', KEYS[1], ARGV[1])
if not raw then return 0 end
local entry = cjson.decode(raw)
local v = entry['version']
if v == nil then v = 0 end
if v ~= tonumber(ARGV[3]) then return 0 end
entry['status'] = 'GREEN'
entry['score'] = tonumber(ARGV[4])
entry['evidence'] = cjson.decode(ARGV[5])
entry['source'] = 'analysis'
entry['version'] = v + 1
entry['missing_aspects'] = {}
redis.call('HSET', KEYS[1], ARGV[1], cjson.encode(entry))
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
return 1
"""

    async def apply_green_signal(
        self,
        question_id: str,
        score: float,
        evidence: list[dict[str, Any]],
        expected_version: int,
    ) -> bool:
        """Apply a green signal only if the question version matches.

        Returns True if applied, False if stale (version mismatch — a manual
        override happened between the analysis read and this write).
        """
        keys = self._keys()
        key = keys.questions(self.session_id)
        result = await self.redis.client.eval(
            self._LUA_APPLY_GREEN,
            1,
            key,
            question_id,
            str(TTL_LIVE),
            str(expected_version),
            str(score),
            json.dumps(evidence),
        )
        return int(result) == 1

    async def update_sufficiency(
        self,
        question_id: str,
        score: float,
        missing_aspects: list[str],
    ) -> None:
        """Store a sub-threshold sufficiency score for G-04 consumption.

        Does not change status or bump version — this is informational, not
        a state transition.
        """
        keys = self._keys()
        key = keys.questions(self.session_id)
        raw = await self.redis.client.hget(key, question_id)
        if raw is None:
            return
        try:
            entry = json.loads(raw)
        except (TypeError, ValueError):
            return
        entry["score"] = score
        entry["missing_aspects"] = missing_aspects
        pipe = self.redis.client.pipeline(transaction=False)
        pipe.hset(key, question_id, json.dumps(entry))
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()

    async def get_question_entry(self, question_id: str) -> dict[str, Any] | None:
        """Read a single question entry from the hash."""
        keys = self._keys()
        key = keys.questions(self.session_id)
        raw = await self.redis.client.hget(key, question_id)
        if raw is None:
            return None
        try:
            entry = json.loads(raw)
            _normalize_array_fields(entry)
            entry["id"] = question_id
            return entry
        except (TypeError, ValueError):
            return None

    # ── Unmapped batches (G-02 AC-2, consumed by G-05) ──────────────

    async def store_unmapped_batch(self, batch_segments: list[dict[str, Any]]) -> None:
        """Retain a batch that mapped to no prepared question for G-05."""
        keys = self._keys()
        key = keys.unmapped(self.session_id)
        pipe = self.redis.client.pipeline(transaction=False)
        pipe.rpush(key, json.dumps(batch_segments))
        pipe.ltrim(key, -500, -1)
        pipe.expire(key, TTL_LIVE)
        await pipe.execute()
