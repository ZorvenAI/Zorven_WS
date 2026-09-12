"""Error taxonomy (Design §18.4, extended by ERRATA-02).

Defined once, here, so every failure surfaces as a typed condition a runbook
can reference rather than an untyped 500. Each code carries its HTTP status,
its WebSocket close code where §10.2.3 assigns one, and whether a caller
should retry.

ERR-01 through ERR-16 are the original §18.4 rows. ERR-17 through ERR-21
were added when the implementation discovered five conditions the taxonomy
had no row for, and five acceptance criteria that cited codes §18.4 assigns
to something else. The full reconciliation is in
``docs/Onboarding_Intelligence/ERRATA-02-error-taxonomy.md``.

This module is the single source of truth for error codes, HTTP statuses,
and operator behaviour. The errata records the reasoning; this code is the
reference.
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

    SKILL_NOT_IN_ALLOWLIST = "ERR-17"
    ILLEGAL_STATE_TRANSITION = "ERR-18"
    AGENT_UNAVAILABLE = "ERR-19"
    SERVICE_TOKEN_INVALID = "ERR-20"
    SERVICE_TOKEN_NOT_CONFIGURED = "ERR-21"


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
    ErrorCode.ILLEGAL_STATE_TRANSITION: ErrorSpec(
        ErrorCode.ILLEGAL_STATE_TRANSITION,
        "Illegal session-state transition (B-04)",
        409,
        None,
        False,
        "State diagram violation; debug the caller",
    ),
    ErrorCode.SERVICE_TOKEN_INVALID: ErrorSpec(
        ErrorCode.SERVICE_TOKEN_INVALID,
        "Missing or incorrect X-Service-Token on an internal endpoint",
        401,
        None,
        False,
        (
            "Check the caller's OIA_SERVICE_TOKEN matches this service's "
            "SERVICE_TOKEN secret; retrying an unchanged token cannot succeed"
        ),
    ),
    ErrorCode.SERVICE_TOKEN_NOT_CONFIGURED: ErrorSpec(
        ErrorCode.SERVICE_TOKEN_NOT_CONFIGURED,
        "This service has no SERVICE_TOKEN set and so authenticates nobody",
        503,
        None,
        # Not retryable, though it is a 503 and it does resolve on its own
        # eventually. Every other retryable=True code clears within seconds
        # and without a human — a degraded dependency recovers, a rate limit
        # expires, a buffered write flushes. This one needs someone to set a
        # secret and redeploy, so the flag would only buy a retry storm across
        # an unbounded window. It also contradicted this spec's own remedy
        # text, which is the same kind of internal disagreement as the
        # code/status mismatch that prompted these codes.
        False,
        (
            "Set the SERVICE_TOKEN secret and redeploy; the service refuses "
            "every caller until then, deliberately"
        ),
    ),
    ErrorCode.AGENT_UNAVAILABLE: ErrorSpec(
        ErrorCode.AGENT_UNAVAILABLE,
        "Django could not reach this service (C-01)",
        503,
        None,
        True,
        (
            "Chat names preparation as temporarily unavailable and points at "
            "the manual path; the caller's circuit breaker opens"
        ),
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
    """ERR-17 — unknown skill id, not in the PG-02 tool allowlist."""

    code = ErrorCode.SKILL_NOT_IN_ALLOWLIST


class RateLimitedError(OIAError):
    """ERR-14 — tenant or user throttle applied (IG-07)."""

    code = ErrorCode.RATE_LIMITED


class SpoolBoundExceeded(OIAError):
    """ERR-16 — GCS spool bound exceeded, recording must stop gracefully."""

    code = ErrorCode.SPOOL_BOUND_EXCEEDED
