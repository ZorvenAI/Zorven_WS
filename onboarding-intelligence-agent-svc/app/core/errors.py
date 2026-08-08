"""Error taxonomy (Design §18.4).

Defined once, here, so every failure surfaces as a typed condition a runbook
can reference rather than an untyped 500. Each code carries its HTTP status,
its WebSocket close code where §10.2.3 assigns one, and whether a caller
should retry.

Two documentation conflicts are resolved here rather than propagated.

**ERR-06 is claimed twice.** §5 PG-02 says an unknown skill id "raises
SkillNotFound and emits ERR-06", but §18.4 assigns ERR-06 to "Live session
already active for company" (409/4409). Emitting it for a bad skill id would
tell an operator that a meeting is already running. :class:`SkillNotFound`
therefore carries a provisional **ERR-17** with a 404, and the documents need
reconciling — either PG-02 names the wrong code or the taxonomy needs a row.

A note on ERR-03 and ERR-04, because A-06's AC-3 conflates them. AC-3 asks for
"the typed ERR-03 authorization error" on an RBAC denial, but §18.4 assigns
ERR-03 to *consent* (IG-08) and **ERR-04 to role denial (PG-03)**. The two have
different operator behaviour — "Consent modal re-presented" versus "Action
hidden or disabled in UI" — so collapsing them would make a permissions bug
look like a consent bug to whoever is on call. ERR-04 is used; the AC wording
is the thing that is wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    """§18.4 taxonomy."""

    INVALID_JWT = "ERR-01"
    TENANT_MISMATCH = "ERR-02"
    CONSENT_MISSING = "ERR-03"
    ROLE_DENIED = "ERR-04"
    SESSION_NOT_FOUND = "ERR-05"
    LIVE_SESSION_ACTIVE = "ERR-06"
    STT_DEGRADED = "ERR-07"
    LLM_DEGRADED = "ERR-08"
    VISION_DEGRADED = "ERR-09"
    BACKEND_WRITE_BUFFERED = "ERR-10"
    GROUNDING_FAILURE = "ERR-11"
    SCHEMA_VALIDATION_FAILURE = "ERR-12"
    FIELD_CONFLICT = "ERR-13"
    RATE_LIMITED = "ERR-14"
    IDEMPOTENCY_CONFLICT = "ERR-15"
    SPOOL_BOUND_EXCEEDED = "ERR-16"

    #: Provisional — see the module docstring. §5 PG-02 asks for ERR-06 here,
    #: but §18.4 has already spent ERR-06 on live-session-active.
    SKILL_NOT_IN_ALLOWLIST = "ERR-17"

    #: Provisional (C-01). Django could not reach this service — 503 or a
    #: timeout. C-01's AC-3 asks for ERR-13, which §18.4 spends on a field
    #: conflict requiring a human (202, SKL-OIA-14) — a different thing with a
    #: different remedy. Nothing existing fits either: ERR-07/08/09 are *this*
    #: service's own degraded dependencies and ERR-10 is a buffered write in
    #: the agent-to-Django direction. There is no code for the reverse.
    AGENT_UNAVAILABLE = "ERR-19"


@dataclass(frozen=True)
class ErrorSpec:
    """One row of the §18.4 table."""

    code: ErrorCode
    condition: str
    http_status: int
    ws_close_code: int | None
    retryable: bool
    operator_behaviour: str


ERROR_SPECS: dict[ErrorCode, ErrorSpec] = {
    ErrorCode.INVALID_JWT: ErrorSpec(
        ErrorCode.INVALID_JWT,
        "Invalid or expired JWT",
        401,
        4401,
        False,
        "Re-authenticate",
    ),
    ErrorCode.TENANT_MISMATCH: ErrorSpec(
        ErrorCode.TENANT_MISMATCH,
        "Tenant mismatch (IG-05)",
        403,
        None,
        False,
        "Blocked, security alert raised",
    ),
    ErrorCode.CONSENT_MISSING: ErrorSpec(
        ErrorCode.CONSENT_MISSING,
        "Consent missing or revoked (IG-08)",
        403,
        4403,
        False,
        "Consent modal re-presented",
    ),
    ErrorCode.ROLE_DENIED: ErrorSpec(
        ErrorCode.ROLE_DENIED,
        "Role denied (PG-03)",
        403,
        None,
        False,
        "Action hidden or disabled in UI",
    ),
    ErrorCode.SESSION_NOT_FOUND: ErrorSpec(
        ErrorCode.SESSION_NOT_FOUND,
        "Session not found or wrong state",
        404,
        4404,
        False,
        "Session list refreshed",
    ),
    ErrorCode.LIVE_SESSION_ACTIVE: ErrorSpec(
        ErrorCode.LIVE_SESSION_ACTIVE,
        "Live session already active for company",
        409,
        4409,
        False,
        "Offer to join or end the existing session",
    ),
    ErrorCode.STT_DEGRADED: ErrorSpec(
        ErrorCode.STT_DEGRADED,
        "STT dependency degraded",
        200,
        None,
        True,
        "RECORD_ONLY banner",
    ),
    ErrorCode.LLM_DEGRADED: ErrorSpec(
        ErrorCode.LLM_DEGRADED,
        "LLM dependency degraded",
        200,
        None,
        True,
        "Manual checkboxes banner",
    ),
    ErrorCode.VISION_DEGRADED: ErrorSpec(
        ErrorCode.VISION_DEGRADED,
        "Vision dependency degraded",
        200,
        None,
        True,
        "Reduced-accuracy OCR badge",
    ),
    ErrorCode.BACKEND_WRITE_BUFFERED: ErrorSpec(
        ErrorCode.BACKEND_WRITE_BUFFERED,
        "Backend write failed, buffered",
        202,
        None,
        True,
        "Saving delayed banner",
    ),
    ErrorCode.GROUNDING_FAILURE: ErrorSpec(
        ErrorCode.GROUNDING_FAILURE,
        "Grounding failure — value dropped (OG-01)",
        200,
        None,
        False,
        "Counted in dropped_ungrounded, shown on review page",
    ),
    ErrorCode.SCHEMA_VALIDATION_FAILURE: ErrorSpec(
        ErrorCode.SCHEMA_VALIDATION_FAILURE,
        "Schema validation failure on model output (OG-04)",
        502,
        None,
        True,
        "One retry with a repair instruction, then escalate",
    ),
    ErrorCode.FIELD_CONFLICT: ErrorSpec(
        ErrorCode.FIELD_CONFLICT,
        "Field conflict requiring a human (SKL-OIA-14)",
        202,
        None,
        False,
        "Escalation card on the review page",
    ),
    ErrorCode.RATE_LIMITED: ErrorSpec(
        ErrorCode.RATE_LIMITED,
        "Rate limited",
        429,
        4429,
        True,
        "Retry-After honoured by the client",
    ),
    ErrorCode.IDEMPOTENCY_CONFLICT: ErrorSpec(
        ErrorCode.IDEMPOTENCY_CONFLICT,
        "Idempotency conflict — same key, different payload",
        409,
        None,
        False,
        "Blocked; indicates a client bug, alerted",
    ),
    ErrorCode.SPOOL_BOUND_EXCEEDED: ErrorSpec(
        ErrorCode.SPOOL_BOUND_EXCEEDED,
        "GCS spool bound exceeded",
        507,
        None,
        False,
        "Recording stopped gracefully with an explicit warning",
    ),
    ErrorCode.SKILL_NOT_IN_ALLOWLIST: ErrorSpec(
        ErrorCode.SKILL_NOT_IN_ALLOWLIST,
        "Unknown skill id — not in the PG-02 tool allowlist",
        404,
        None,
        False,
        "Indicates a caller or configuration bug, not a user error",
    ),
}


class OIAError(Exception):
    """Base for every typed failure this service raises."""

    code: ErrorCode = ErrorCode.SCHEMA_VALIDATION_FAILURE

    def __init__(self, message: str = "", **context: object) -> None:
        self.spec = ERROR_SPECS[self.code]
        self.message = message or self.spec.condition
        self.context = context
        super().__init__(f"{self.code.value}: {self.message}")

    @property
    def http_status(self) -> int:
        return self.spec.http_status

    @property
    def ws_close_code(self) -> int | None:
        return self.spec.ws_close_code

    @property
    def retryable(self) -> bool:
        return self.spec.retryable

    def to_body(self) -> dict[str, object]:
        """The standard error body (§18.4).

        Deliberately carries no request payload: an authorization failure is
        logged and returned without echoing what was attempted.
        """
        return {
            "error_code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }


class AuthorizationError(OIAError):
    """ERR-04 — role denied by the §15 matrix at PG-03."""

    code = ErrorCode.ROLE_DENIED


class ConsentError(OIAError):
    """ERR-03 — consent missing or revoked (IG-08)."""

    code = ErrorCode.CONSENT_MISSING


class TenantMismatchError(OIAError):
    """ERR-02 — the tenant header disagrees with the JWT claim (IG-05)."""

    code = ErrorCode.TENANT_MISMATCH


class SkillNotFound(OIAError):
    """An unknown skill id — PG-02's tool allowlist rejected it.

    Carries the provisional ERR-17 rather than the ERR-06 that PG-02 names,
    because §18.4 assigns ERR-06 to "Live session already active for company"
    with 409/4409. Reusing it would tell an operator a meeting is already
    running when the truth is that a skill id is wrong. See the module
    docstring; the documents need reconciling.
    """

    code = ErrorCode.SKILL_NOT_IN_ALLOWLIST


class RateLimitedError(OIAError):
    """ERR-14 — tenant or user throttle applied (IG-07)."""

    code = ErrorCode.RATE_LIMITED
