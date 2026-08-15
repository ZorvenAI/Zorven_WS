"""Request and response models for the HTTP and WebSocket surfaces.

Design §10.2 · scaffolded by A-05, the PREP envelope implemented by C-01.

The shapes below are §10.2.1 verbatim. The C-01 card is unusually firm about
this — "implement them exactly; C-02 through C-04 all ride this envelope" —
so the field names are copied from the design rather than tidied, and
``model_config`` forbids extras so a typo in a caller fails loudly instead of
being silently dropped.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TenantContext(BaseModel):
    """Who is asking, and under what trace (§10.2.1, §15).

    The role is read from here and never from a request body field the caller
    could set independently — §15 says roles come from the verified JWT claim
    only. Django has already verified it; this is the propagation.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    user_id: str
    role: Literal["OWNER", "ADMIN", "EDITOR", "VIEWER"]
    trace_id: str
    correlation_id: str | None = None


class ExecuteRequest(BaseModel):
    """``POST /v1/execute`` — a PREP turn (§10.2.1)."""

    model_config = ConfigDict(extra="forbid")

    tenant_context: TenantContext
    session_id: str | None = Field(
        default=None,
        description=(
            "The onboarding session, when one exists. A prep conversation "
            "starts before it does, so this is optional — chat_session_id is "
            "what conversation state is keyed on."
        ),
    )
    chat_session_id: str = Field(
        description="The chat this turn belongs to; the conversation-state key"
    )
    input_prompt: str
    input_context: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    previous_outputs: dict[str, Any] = Field(default_factory=dict)


class GuardrailReport(BaseModel):
    """The three gate verdicts (§5). Reported on every response, because a
    caller cannot otherwise tell a clean pass from a gate that never ran."""

    model_config = ConfigDict(extra="forbid")

    input: Literal["PASS", "FAIL"] = "PASS"
    plan: Literal["PASS", "FAIL"] = "PASS"
    output: Literal["PASS", "FAIL"] = "PASS"


class UsageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


class ExecuteResponse(BaseModel):
    """``POST /v1/execute`` 200 (§10.2.1).

    ``output`` is deliberately untyped: §10.2.1 shows a questionnaire draft,
    but C-02 through C-04 put different skill outputs in the same envelope.
    Typing it to the questionnaire shape now would make this envelope a lie
    for three of the four stories that ride it.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["SUCCEEDED", "FAILED"]
    skill_id: str
    prompt_version: dict[str, str] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    guardrails: GuardrailReport = Field(default_factory=GuardrailReport)
    usage: UsageReport = Field(default_factory=UsageReport)


# ── Live frames (F-04 PR 2, Design §10.2.3) ──────────────────────────
#
# Pydantic models rather than hand-built dicts, which AC-4 asks for by name:
# "the frame shapes match Design §10.2.3 exactly, validated against a shared
# schema module rather than hand-built dicts". Shared with the tests, so a
# shape change breaks a test rather than a browser.


class ClientFrameType(str, Enum):
    """Client → server control frames. Binary audio carries no envelope."""

    START = "start"
    RESUME = "resume"
    MARK_QUESTION = "mark_question"
    STOP = "stop"


class ServerFrameType(str, Enum):
    """Server → client frames. Always JSON, always carrying seq."""

    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"
    GREEN_SIGNAL = "green_signal"
    FOLLOWUPS = "followups"
    NOTABLE_FACT = "notable_fact"
    COVERAGE = "coverage"
    ERROR = "error"
    #: Not in §10.2.3's list, and required by AC-3: "a resume attempt beyond
    #: the window is answered with an explicit resync frame, not a silent gap
    #: in seq". A client that cannot tell "nothing happened" from "we dropped
    #: your history" will render a meeting with a hole in it.
    RESYNC = "resync"


class ServerFrame(BaseModel):
    """The envelope every server frame shares.

    `seq` is required and has no default. A frame built without one would be
    silently unordered, and AC-4's invariant — strictly increasing across all
    frame types, for the life of the session — is exactly the kind that holds
    until one code path forgets.
    """

    model_config = ConfigDict(extra="forbid")

    type: ServerFrameType
    seq: int = Field(ge=1)


class TranscriptPartial(ServerFrame):
    type: Literal[ServerFrameType.TRANSCRIPT_PARTIAL] = (
        ServerFrameType.TRANSCRIPT_PARTIAL
    )
    text: str
    speaker: int


class TranscriptFinal(ServerFrame):
    type: Literal[ServerFrameType.TRANSCRIPT_FINAL] = ServerFrameType.TRANSCRIPT_FINAL
    text: str
    speaker: int
    t_start: float
    t_end: float
    redaction_applied: bool = False


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recording_id: str
    t_start: float
    t_end: float


class GreenSignal(ServerFrame):
    type: Literal[ServerFrameType.GREEN_SIGNAL] = ServerFrameType.GREEN_SIGNAL
    question_id: str
    score: float
    #: FR-LIVE-04: "every mapping carries a resolvable {recording_id, t_start,
    #: t_end}; a mapping whose span does not resolve is dropped, not shown".
    evidence: list[EvidenceSpan]


class Followups(ServerFrame):
    type: Literal[ServerFrameType.FOLLOWUPS] = ServerFrameType.FOLLOWUPS
    question_id: str
    #: FR-LIVE-07 caps this at three per question. Enforced here so a skill
    #: cannot exceed it by building a dict.
    suggestions: list[str] = Field(max_length=3)


class NotableFact(ServerFrame):
    type: Literal[ServerFrameType.NOTABLE_FACT] = ServerFrameType.NOTABLE_FACT
    text: str
    workflow_target: Literal["WF1", "WF2", "WF3"]


class Coverage(ServerFrame):
    type: Literal[ServerFrameType.COVERAGE] = ServerFrameType.COVERAGE
    #: FR-LIVE-09: three fractions, "never blended into one percentage
    #: anywhere in the UI or the API". A single number here would be the
    #: blending that requirement forbids.
    map: dict[Literal["WF1", "WF2", "WF3"], float]


class ErrorFrame(ServerFrame):
    type: Literal[ServerFrameType.ERROR] = ServerFrameType.ERROR
    code: str
    message: str
    recoverable: bool


class Resync(ServerFrame):
    """AC-3's explicit answer to a resume the buffer cannot satisfy."""

    type: Literal[ServerFrameType.RESYNC] = ServerFrameType.RESYNC
    #: The oldest seq still replayable. The client knows precisely what it
    #: missed rather than inferring it from a gap.
    from_seq: int
    reason: str = "resume window exceeded"


class StartFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ClientFrameType.START] = ClientFrameType.START
    recording_id: str
    codec: str
    sample_rate: int


class ResumeFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ClientFrameType.RESUME] = ClientFrameType.RESUME
    last_seq: int = Field(ge=0)


class MarkQuestionFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ClientFrameType.MARK_QUESTION] = ClientFrameType.MARK_QUESTION
    question_id: str
    action: str


class StopFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[ClientFrameType.STOP] = ClientFrameType.STOP
