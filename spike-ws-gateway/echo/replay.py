"""Capped replay buffer backing zero-token reconnect (Design §9.2).

On reconnect the client sends ``last_seq`` and the server replays the frames
after it from this buffer rather than re-running any model. Reconnect
therefore costs zero tokens and is bounded by buffer length.

The spike keeps the buffer in memory. F-04 moves it to a capped Redis list
under ``oia:v1:{tenant}:live:{session_id}:frames`` (ERRATA-01: DB 2, not 27).
The interface here is the one F-04 inherits.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of a resume request.

    ``frames`` is the replayable suffix. When ``resync_required`` is set the
    client asked for a point that has already been trimmed, and the caller
    must answer with an explicit resync frame rather than a silent gap.
    """

    frames: list[dict]
    resync_required: bool
    oldest_available_seq: int | None


class ReplayBuffer:
    """Fixed-capacity, seq-ordered buffer of server → client frames."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._frames: deque[dict] = deque(maxlen=capacity)

    def append(self, frame: dict) -> None:
        if "seq" not in frame:
            raise ValueError("every buffered frame must carry a seq")
        if self._frames and frame["seq"] <= self._frames[-1]["seq"]:
            raise ValueError(
                f"seq must strictly increase: got {frame['seq']} "
                f"after {self._frames[-1]['seq']}"
            )
        self._frames.append(frame)

    def resume(self, last_seq: int) -> ReplayResult:
        """Return every frame with seq > last_seq.

        A client that is fully caught up gets an empty replay, which is a
        success, not a resync. A client asking for a seq older than anything
        retained gets ``resync_required`` — the window has moved past it.
        """
        oldest = self._frames[0]["seq"] if self._frames else None

        if not self._frames:
            return ReplayResult([], False, None)

        # last_seq predates the retained window: frames were trimmed away.
        if last_seq < oldest - 1:
            return ReplayResult([], True, oldest)

        return ReplayResult(
            [f for f in self._frames if f["seq"] > last_seq], False, oldest
        )

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._frames)
