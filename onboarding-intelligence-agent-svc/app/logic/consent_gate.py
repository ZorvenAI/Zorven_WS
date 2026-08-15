"""IG-08 — recording requires consent that is present and still valid.

Design §5.1 IG-08, §10.1 ConsentRecord · story F-01 · FR-GDPR-01, FR-REC-01.

Split into policy and I/O on purpose:

- :func:`consent_verdict` is pure. Given a consent state it returns a Verdict.
  Every branch — absent, revoked, unverifiable — is testable without a socket
  or a server, and the branches are the part that has to be right.
- :func:`fetch_consent_state` is the read from Django, service-token
  authenticated. IG-08 says the record is "verified server-side against Django
  — never trusted from the client", and this is where that holds.

The card asks for "three places, one function": the WS accept path, POST
/v1/process and every start control frame. Two of those do not exist yet —
/v1/process is J-01's and control frames are F-04's — so today only the WS
path calls it. The shape is what makes adding the other two a one-liner
instead of a second implementation that drifts.

The close code is **4403**, not the 4401 in §5.1's IG-08 row. The card's AC-3,
the ERR-03 taxonomy row, FR-LIVE-01 and FR-GDPR-01 all say 4403, and 4401 is
the code for an invalid JWT — reusing it here would make a consent failure
indistinguishable from an auth failure to every client. Raised on #555.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.logic.guardrails import Action, Verdict

logger = logging.getLogger(__name__)

RULE_ID = "IG-08"

#: §10.2.3 and FR-LIVE-01: "4403 consent missing or revoked".
CLOSE_FORBIDDEN = 4403

#: The operator-facing reason. Short, because a WebSocket close reason is
#: capped at 123 bytes and some clients silently drop a longer one.
CONSENT_REQUIRED = "consent_required"

#: How often an open session re-checks (AC-4: "within 5 seconds").
#:
#: Three, not five. A five-second poll cannot meet a five-second budget — a
#: revocation landing one moment after a check waits most of a full interval
#: before the next one, and then has to be acted on. Same arithmetic as D-03's
#: sync cadence.
WATCH_INTERVAL_S = 3.0


@dataclass(frozen=True)
class ConsentState:
    """What Django says about one session's consent.

    ``reachable`` is separate from ``present`` because "there is no consent"
    and "we could not find out" are different facts with the same safe answer
    but different operator-facing wording — and conflating them would make an
    outage look like a compliance failure to whoever reads the logs.
    """

    present: bool
    active: bool
    reachable: bool = True
    consent_id: str | None = None
    #: Never sent to a client and never logged. Held only so a caller that has
    #: it cannot accidentally be the one place it leaks — see the test.
    subject_name: str = ""


def consent_verdict(state: ConsentState) -> Verdict:
    """IG-08's decision. Pure, and the only place the policy lives.

    Fails closed on every uncertainty. §5: "on breach, fail closed and emit
    EVT-004". An agent that recorded because it could not reach Django would
    produce exactly the artefact FR-GDPR-01 exists to prevent, during an
    outage, when nobody is reading logs.
    """
    if not state.reachable:
        return Verdict(
            rule_id=RULE_ID,
            action=Action.BLOCK,
            detail=(
                f"{CONSENT_REQUIRED}: consent could not be verified with the "
                "backend."
            ),
        )

    if not state.present:
        return Verdict(
            rule_id=RULE_ID,
            action=Action.BLOCK,
            detail=f"{CONSENT_REQUIRED}: no consent has been recorded.",
        )

    if not state.active:
        return Verdict(
            rule_id=RULE_ID,
            action=Action.BLOCK,
            detail=f"{CONSENT_REQUIRED}: consent was revoked.",
        )

    return Verdict(rule_id=RULE_ID, action=Action.PASS)


def as_rule(state: ConsentState) -> Callable[[Any, Any], Verdict]:
    """Adapt the verdict to the chain's synchronous Rule signature.

    The chain calls rules with (payload, context) and no I/O, which is right:
    a guardrail that can block on a network read is a guardrail that can hang
    the request it is protecting. The state is fetched by the caller and closed
    over here, so the chain still emits EVT-004 through its own machinery
    rather than this module hand-rolling an event.
    """

    def _evaluate(payload: Any, context: Any) -> Verdict:  # noqa: ARG001
        return consent_verdict(state)

    return _evaluate


async def fetch_consent_state(
    backend: Any, *, tenant_id: str, session_id: str
) -> ConsentState:
    """Read consent from Django's live-precheck.

    The same endpoint IG-10 uses, extended by this story rather than joined by
    a second one — its own docstring makes the argument: "Two reads to decide
    one thing is two chances to decide it on a stale half."
    """
    if backend is None or not getattr(backend, "configured", False):
        return ConsentState(present=False, active=False, reachable=False)

    try:
        body = await backend.live_precheck(tenant_id=tenant_id, session_id=session_id)
    except Exception as exc:  # noqa: BLE001 - fail closed on anything
        logger.warning(
            "consent_precheck_failed",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )
        return ConsentState(present=False, active=False, reachable=False)

    if not isinstance(body, dict):
        return ConsentState(present=False, active=False, reachable=False)

    consent = body.get("consent")
    if not isinstance(consent, dict):
        # An older backend that does not report consent yet. Refusing is the
        # only safe reading: silently passing would mean a deploy-order
        # mismatch turns the gate off without anyone choosing that.
        logger.warning("consent_precheck_missing_consent_block")
        return ConsentState(present=False, active=False, reachable=False)

    return ConsentState(
        present=bool(consent.get("present")),
        active=bool(consent.get("active")),
        reachable=True,
        consent_id=consent.get("consent_id"),
    )


async def watch_consent(
    poll: Callable[[], Awaitable[ConsentState]],
    *,
    on_revoked: Callable[[Verdict], Any],
    interval_s: float = WATCH_INTERVAL_S,
    stop_after: int | None = None,
) -> None:
    """Re-check consent for the life of an open session (AC-4).

    A single evaluation on connect is not enough, and the card says so: B-07's
    revocation path fires mid-session. Consent granted at the start of a
    forty-five minute meeting is not consent at minute thirty.

    F-04 mounts this on the socket it keeps open. It is a free function taking
    a `poll` callable rather than a method on the socket handler so it can be
    tested — and was tested — before that socket exists.

    Returns when consent is revoked, when `stop_after` polls have run, or when
    the task is cancelled.
    """
    polls = 0
    while stop_after is None or polls < stop_after:
        state = await poll()
        polls += 1

        verdict = consent_verdict(state)
        if verdict.blocked:
            logger.info(
                "consent_revoked_mid_session",
                extra={"rule_id": RULE_ID, "detail": verdict.detail},
            )
            on_revoked(verdict)
            return

        if interval_s:
            await asyncio.sleep(interval_s)


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def emit_refusal(
    events: Any,
    verdict: Verdict,
    *,
    tenant_id: str,
    session_id: str,
    correlation_id: str = "",
) -> None:
    """EVT-004 for an IG-08 refusal (AC-3).

    Lives here rather than at each call site so "three places, one function"
    stays true of the *whole* refusal — the decision and the record of it —
    and not only of the decision. A call site that closes the socket but
    forgets the event leaves a compliance refusal invisible, which is the half
    that matters after the fact.

    Emitted here rather than left to GuardrailChain because the chain's
    ``_emit_triggered`` only logs: its ``_emitter`` is stored and never used,
    despite the docstring saying "every trigger is an event, not just a log
    line". That gap predates this story and is reported separately; F-01 does
    not fix it by quietly restructuring a synchronous path every rule shares.

    Never raises. A refusal that failed to be recorded must still be a refusal.
    """
    if events is None:
        return

    try:
        from app.events.catalog import EventType

        await events.emit(
            EventType.AGENT_GUARDRAIL_TRIGGERED,
            tenant_id=tenant_id,
            correlation_id=correlation_id or f"ig08-{session_id}",
            # Omitted rather than passed through when it is not a UUID. The
            # envelope validates both ids, and a non-UUID session id would
            # raise inside build() and lose the *whole* event — the refusal
            # would go unrecorded because an identifier was the wrong shape.
            # Production ids are UUIDs; this only bites a hand-rolled caller.
            session_id=_as_uuid(session_id),
            outcome="FAILURE",
            payload={
                "rule_id": RULE_ID,
                # §5's EVT-004 is "payload.rule_id and the action taken".
                "action": verdict.action.value,
                "detail": verdict.detail,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "consent_refusal_event_failed",
            extra={"error": f"{type(exc).__name__}: {exc}"},
        )
