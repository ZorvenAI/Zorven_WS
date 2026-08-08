"""Request and response models for the HTTP and WebSocket surfaces.

Design §10.2 · scaffolded by A-05, the PREP envelope implemented by C-01.

The shapes below are §10.2.1 verbatim. The C-01 card is unusually firm about
this — "implement them exactly; C-02 through C-04 all ride this envelope" —
so the field names are copied from the design rather than tidied, and
``model_config`` forbids extras so a typo in a caller fails loudly instead of
being silently dropped.
"""

from __future__ import annotations

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
