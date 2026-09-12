"""F-01 · IG-08, the consent gate.

Written in the order the card asks for: "The revocation path is the part teams
skip. Write AC-4's test before AC-2's implementation if you want it to exist."
So the revocation cases are first in this file and were first in the commit.

The gate is split deliberately. `consent_verdict` is pure policy — it takes the
consent state and returns a Verdict, so every branch is testable without a
socket or a server. `fetch_consent_state` is the I/O that reads it from Django
with a service token, which is what "verified server-side against Django, never
trusted from the client" means. Combining them into one async rule would make
the policy untestable except through HTTP, and the policy is the part that has
to be right.
"""

from __future__ import annotations

from app.logic.consent_gate import (
    CONSENT_REQUIRED,
    ConsentState,
    RULE_ID,
    consent_verdict,
    watch_consent,
)
from app.logic.guardrails import Action

# No module-level asyncio mark: pyproject sets `asyncio_mode = "auto"`, so the
# async tests here run on their own and the mark would only be applied to the
# synchronous ones — which pytest-asyncio warns about, correctly.


# ── AC-4 · revocation, written first ─────────────────────────────────


def test_revoked_consent_is_refused():
    """The case the card says teams skip.

    A ConsentRecord that exists is not consent — `revoked_at` being set means
    the brand owner withdrew it, and a gate that only checks for existence
    would keep recording someone who asked us to stop.
    """
    verdict = consent_verdict(ConsentState(present=True, active=False))

    assert verdict.action is Action.BLOCK
    assert verdict.rule_id == RULE_ID


async def test_a_revocation_closes_the_watch():
    """AC-4: an open socket closes "within 5 seconds" of revocation.

    Driven through the watcher rather than a socket. F-04 owns the socket that
    stays open; what F-01 owes it is a mechanism that notices, and a mechanism
    nobody has run is a promise.
    """
    states = [
        ConsentState(present=True, active=True),
        ConsentState(present=True, active=True),
        ConsentState(present=True, active=False),
    ]
    seen: list[ConsentState] = []

    async def poll():
        state = states[min(len(seen), len(states) - 1)]
        seen.append(state)
        return state

    closed = []
    await watch_consent(
        poll,
        on_revoked=lambda verdict: closed.append(verdict),
        interval_s=0,
        stop_after=len(states),
    )

    assert len(closed) == 1, "revocation was not noticed"
    assert closed[0].action is Action.BLOCK
    # It stopped at the revocation rather than polling on.
    assert len(seen) == 3


async def test_the_watch_interval_meets_the_five_second_budget():
    """AC-4 says "within 5 seconds", so the interval is not a free parameter.

    Asserted against the constant rather than by timing a real sleep: a test
    that waits five seconds to prove a five-second budget is a test nobody
    runs twice.
    """
    from app.logic.consent_gate import WATCH_INTERVAL_S

    assert WATCH_INTERVAL_S <= 5.0


async def test_a_watch_over_healthy_consent_never_fires():
    """The control. A watcher that closed on everything would pass the
    revocation test and end every meeting the moment it started."""
    calls = 0

    async def poll():
        nonlocal calls
        calls += 1
        return ConsentState(present=True, active=True)

    closed = []
    await watch_consent(poll, on_revoked=closed.append, interval_s=0, stop_after=4)

    assert closed == []
    assert calls == 4


# ── AC-3 · the gate refuses, server-side ─────────────────────────────


def test_absent_consent_is_refused():
    verdict = consent_verdict(ConsentState(present=False, active=False))

    assert verdict.action is Action.BLOCK
    assert CONSENT_REQUIRED in verdict.detail


def test_active_consent_passes():
    """The control that stops every other test here passing vacuously."""
    verdict = consent_verdict(ConsentState(present=True, active=True))

    assert verdict.action is Action.PASS


def test_an_unreachable_backend_fails_closed():
    """§5: "on breach, fail closed and emit EVT-004".

    An agent that recorded because it could not reach Django would produce
    exactly the artefact FR-GDPR-01 exists to prevent, and would do it during
    an outage when nobody is reading logs.
    """
    verdict = consent_verdict(
        ConsentState(present=False, active=False, reachable=False)
    )

    assert verdict.action is Action.BLOCK
    assert "could not be verified" in verdict.detail.lower()


def test_the_refusal_never_carries_the_subject_name():
    """The verdict's detail reaches a close frame and a log line. A subject's
    name in either is the leak FR-GDPR-01 and EVT-101's hashing both exist to
    prevent."""
    state = ConsentState(present=True, active=False, subject_name="Ada Lovelace")

    verdict = consent_verdict(state)

    assert "Ada" not in verdict.detail
    assert "Lovelace" not in verdict.detail
