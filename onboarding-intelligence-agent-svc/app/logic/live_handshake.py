"""What has to be true before a live socket is accepted (F-04 PR 1, AC-1).

Design §10.2.3 · NFR-SEC-02 · spike A-02.

AC-1 lists five things — JWT validated, tenant resolved, role checked, consent
verified, session live-eligible — and says all of them happen "before
accept()". They resolve from **one** call to Django's live-precheck, which the
handshake already made for IG-10: the response carries the ticket's claims, the
questionnaire's approval and the consent state together. Two reads to decide
one thing is two chances to decide it on a stale half.

The agent verifies no signatures. Django signs HS256 with `SECRET_KEY`, which
also derives the Fernet key protecting every tenant's OAuth refresh tokens;
shipping it here so this module could check a signature would put those inside
an agent compromise. A ticket is a lookup key into a store only Django writes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.logic.consent_gate import ConsentState, consent_verdict

logger = logging.getLogger(__name__)

# ── §10.2.3's close codes, as named constants ────────────────────────
#
# NFR-SEC-02 asks for them by name rather than as literals, and there are
# **six**: the card's AC-1 lists five and omits 1011, which §10.2.3 defines as
# "internal error with retry advised". A client that cannot tell a bug from a
# refusal retries the wrong one.
CLOSE_UNAUTHORIZED = 4401  # invalid or expired ticket
CLOSE_FORBIDDEN = 4403  # consent missing or revoked (IG-08)
CLOSE_NOT_FOUND = 4404  # session not found or not live-eligible
CLOSE_CONFLICT = 4409  # another socket already live for this session
CLOSE_RATE_LIMITED = 4429  # rate limited
CLOSE_INTERNAL = 1011  # internal error, retry advised

CLOSE_CODES: dict[str, int] = {
    "unauthorized": CLOSE_UNAUTHORIZED,
    "forbidden": CLOSE_FORBIDDEN,
    "not_found": CLOSE_NOT_FOUND,
    "conflict": CLOSE_CONFLICT,
    "rate_limited": CLOSE_RATE_LIMITED,
    "internal": CLOSE_INTERNAL,
}

#: §15's live roles. A Viewer may read a session and may not run a meeting.
LIVE_ROLES = frozenset({"owner", "admin", "editor"})


@dataclass(frozen=True)
class Handshake:
    """The verdict, and the identity behind it when there is one."""

    code: int | None
    reason: str = ""
    tenant_id: str = ""
    company_id: str = ""
    user_id: str = ""
    role: str = ""
    valid_until: str = ""

    @property
    def refused(self) -> bool:
        return self.code is not None


def _refuse(code: int, reason: str) -> Handshake:
    # Reasons are short: a WebSocket close reason is capped at 123 bytes and
    # some clients silently drop a longer one, turning a helpful refusal into
    # a bare code.
    return Handshake(code=code, reason=reason[:120])


def evaluate(precheck: Any) -> Handshake:
    """Decide the handshake from one precheck response.

    Order matters and follows the question's own dependency: who are you,
    then may we record you, then is there a meeting to join. Asking about the
    questionnaire before the ticket would tell an unauthenticated caller
    whether a session exists.
    """
    if not isinstance(precheck, dict):
        # The backend was unreachable or answered nonsense. 1011, not 4401:
        # this is our failure, and telling the client its credentials are bad
        # sends it to re-authenticate against a problem that is not there.
        return _refuse(CLOSE_INTERNAL, "The service could not verify this session.")

    if precheck.get("__status__") == 404:
        # Django answers 404 for a session outside the caller's tenant, so this
        # is also the cross-tenant case. 4404 says "not found" without
        # confirming whether it exists somewhere else, which is what
        # FR-PREP-06 requires of the REST path and should be true here too.
        return _refuse(CLOSE_NOT_FOUND, "Session not found or not live-eligible.")

    auth = precheck.get("auth")
    if not isinstance(auth, dict) or not auth.get("valid"):
        return _refuse(CLOSE_UNAUTHORIZED, "Invalid or expired ticket.")

    role = str(auth.get("role") or "").lower()
    if role not in LIVE_ROLES:
        # 4403 rather than 4401: the caller is who they say they are, and the
        # answer is still no. Re-authenticating would not help.
        return _refuse(
            CLOSE_FORBIDDEN, f"Role {role or 'unknown'} cannot run a meeting."
        )

    # Delegated to F-01's rule rather than re-decided here. It distinguishes
    # "no consent has been recorded" from "consent was revoked", and that
    # difference is the whole of what the operator does next — one is a modal
    # to fill in, the other is a conversation to have. Flattening both into
    # one string, which the first version of this function did, loses it.
    consent = precheck.get("consent")
    consent_state = ConsentState(
        present=bool(isinstance(consent, dict) and consent.get("present")),
        active=bool(isinstance(consent, dict) and consent.get("active")),
        reachable=isinstance(consent, dict),
    )
    refusal = consent_verdict(consent_state)
    if refusal.blocked:
        return _refuse(CLOSE_FORBIDDEN, refusal.detail)

    if not precheck.get("approved"):
        # Not live-eligible. §10.2.3 gives 4404 this meaning as well as a
        # missing session, and the reason string is what separates them for a
        # human reading a console.
        reason = str(precheck.get("reason") or "This session cannot start a meeting.")
        return _refuse(CLOSE_NOT_FOUND, reason)

    return Handshake(
        code=None,
        tenant_id=str(auth.get("tenant_id") or ""),
        company_id=str(auth.get("company_id") or ""),
        user_id=str(auth.get("user_id") or ""),
        role=role,
        valid_until=str(auth.get("valid_until") or ""),
    )


def expired(valid_until: str, *, now: datetime | None = None) -> bool:
    """Whether the authorisation behind an open socket has run out.

    NFR-SEC-02: "a token that expires mid-session closes the socket with 4401,
    **not at the next message boundary**". An idle socket is the case that
    matters — a meeting where nobody is speaking still holds an open
    connection, and waiting for traffic to notice an expiry means never
    noticing it.

    Unparseable counts as expired. A value we cannot read is not a value we
    can rely on, and failing closed on authentication is the only safe
    direction.
    """
    if not valid_until:
        return True
    try:
        deadline = datetime.fromisoformat(valid_until)
    except ValueError:
        logger.warning("live_valid_until_unparseable")
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) >= deadline
