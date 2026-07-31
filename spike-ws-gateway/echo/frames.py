"""Server → client frame contracts and close codes.

These mirror Design §10.2.3 exactly. F-04 inherits this module rather than
hand-building dicts, so a frame-shape change breaks a test rather than a
browser.

Every server → client frame carries a monotonic ``seq`` that is strictly
increasing for the life of the session across all frame types (§9.2).
"""

from __future__ import annotations

import itertools
from enum import IntEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CloseCode(IntEnum):
    """WebSocket close codes from Design §10.2.3.

    The frontend behaves differently per code, so they are explicit rather
    than collapsed into a generic failure.
    """

    INVALID_JWT = 4401
    CONSENT_MISSING = 4403
    SESSION_NOT_FOUND = 4404
    ALREADY_LIVE = 4409
    RATE_LIMITED = 4429
    INTERNAL_ERROR = 1011


class _ServerFrame(BaseModel):
    seq: int = Field(..., ge=0)


class Evidence(BaseModel):
    recording_id: str
    t_start: float
    t_end: float


class TranscriptPartial(_ServerFrame):
    type: Literal["transcript.partial"] = "transcript.partial"
    text: str
    speaker: int


class TranscriptFinal(_ServerFrame):
    type: Literal["transcript.final"] = "transcript.final"
    text: str
    speaker: int
    t_start: float
    t_end: float
    redaction_applied: bool = False


class GreenSignal(_ServerFrame):
    type: Literal["green_signal"] = "green_signal"
    question_id: str
    score: float
    evidence: list[Evidence] = Field(default_factory=list)


class Followups(_ServerFrame):
    type: Literal["followups"] = "followups"
    question_id: str
    suggestions: list[str]


class NotableFact(_ServerFrame):
    type: Literal["notable_fact"] = "notable_fact"
    text: str
    workflow_target: str


class Coverage(_ServerFrame):
    type: Literal["coverage"] = "coverage"
    map: dict[str, float]


class ErrorFrame(_ServerFrame):
    type: Literal["error"] = "error"
    code: str
    message: str
    recoverable: bool


class Resync(_ServerFrame):
    """Answer to a resume beyond the replay window.

    Design §10.2.3 does not enumerate this frame, but F-04 AC-3 requires that
    an out-of-window resume is answered explicitly rather than with a silent
    gap in seq. The spike proves the shape; F-04 inherits it.
    """

    type: Literal["resync"] = "resync"
    reason: str
    oldest_available_seq: int | None


class EchoAck(_ServerFrame):
    """Spike-only: acknowledges a binary audio frame so RTT can be paired.

    Not part of §10.2.3. The real service replies with transcript frames; the
    echo needs a correlatable ack to measure round-trip time per frame.
    """

    type: Literal["echo.ack"] = "echo.ack"
    echo_id: int
    bytes_received: int
    # Which process answered. On Cloud Run this is how the harness tells
    # whether a reconnect landed on the same instance.
    instance: str = ""


ServerFrame = Annotated[
    Union[
        TranscriptPartial,
        TranscriptFinal,
        GreenSignal,
        Followups,
        NotableFact,
        Coverage,
        ErrorFrame,
        Resync,
        EchoAck,
    ],
    Field(discriminator="type"),
]


class SeqAllocator:
    """Hands out the monotonic seq series for one session.

    Strictly increasing across every frame type, for the life of the session,
    including across reconnects — the series continues rather than restarting
    (Design §9.2).
    """

    def __init__(self, start: int = 0) -> None:
        self._counter = itertools.count(start)
        self._last = start - 1

    def next(self) -> int:
        self._last = next(self._counter)
        return self._last

    @property
    def last(self) -> int:
        return self._last
