"""Short-lived, single-purpose tickets for the live WebSocket (F-04).

Spike A-02, finding 2, in as many words:

    F-04 and the frontend should use short-lived, single-purpose tokens for
    the socket rather than the long-lived session JWT.

The reason is that browsers cannot set headers on a WebSocket handshake, so the
token travels as ``?jwt=`` and lands in gateway logs, browser history and any
proxy in between. A session JWT there is a 60-minute credential for the whole
API sitting in a log file; a ticket is a few seconds of permission to open one
socket for one session.

**The agent never verifies a signature.** Django signs its JWTs HS256 with
``SECRET_KEY``, and that same key derives the Fernet key protecting every
tenant's OAuth refresh tokens (``automation/encryption.py``). Shipping it to the
agent so it can check a signature would mean a compromised agent can decrypt
every connected Google and social account. The agent asks Django instead, on
the ``live-precheck`` call it already makes at handshake.

Two lifetimes, deliberately:

- ``usable_until`` — how long the ticket can *open* a socket. Seconds. A ticket
  that leaked into a log is worthless almost immediately.
- ``valid_until`` — how long the authorisation it granted *lasts*. Inherited
  from the JWT that minted it, so NFR-SEC-02 holds: "a token that expires
  mid-session closes the socket with 4401, not at the next message boundary."

Collapsing them into one value gets you either a socket that dies a minute
after it opens, or a ticket that stays usable for an hour.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

#: How long a freshly minted ticket can open a socket.
USABLE_SECONDS = 60

#: Fallback session length when the caller's token carries no expiry we can
#: read. Matches SIMPLE_JWT's ACCESS_TOKEN_LIFETIME so behaviour does not
#: change silently depending on which path minted the ticket.
DEFAULT_VALID_MINUTES = 60

CACHE_PREFIX = "oia:live-ticket:"


@dataclass(frozen=True)
class TicketClaims:
    """Everything the agent's handshake needs, resolved once by Django."""

    session_id: str
    tenant_id: str
    company_id: str
    user_id: str
    role: str
    #: ISO-8601. The socket closes 4401 when this passes (NFR-SEC-02).
    valid_until: str


def _key(ticket: str) -> str:
    return f"{CACHE_PREFIX}{ticket}"


def mint(*, session, user, role: str, valid_until=None) -> tuple[str, TicketClaims]:
    """Issue a ticket for one session and return ``(ticket, claims)``.

    The ticket is a random string, not a signed blob. There is nothing to
    verify offline and nothing to forge: it is a lookup key into a store only
    Django writes, which is what lets the agent hold no key material at all.
    """
    expiry = valid_until or (timezone.now() + timedelta(minutes=DEFAULT_VALID_MINUTES))
    claims = TicketClaims(
        session_id=str(session.pk),
        tenant_id=str(session.tenant_id or ""),
        company_id=str(session.company_id or ""),
        user_id=str(getattr(user, "pk", "") or ""),
        role=role,
        valid_until=expiry.isoformat(),
    )

    ticket = secrets.token_urlsafe(32)
    cache.set(_key(ticket), asdict(claims), timeout=USABLE_SECONDS)
    return ticket, claims


def resolve(ticket: str) -> TicketClaims | None:
    """The claims behind a ticket, or None if it never existed or has aged out.

    Deliberately does not distinguish the two. Telling a caller that a ticket
    *was* valid narrows the search for one that still is.
    """
    if not ticket:
        return None
    stored = cache.get(_key(str(ticket)))
    if not isinstance(stored, dict):
        return None
    try:
        return TicketClaims(**stored)
    except TypeError:
        # A stored shape from an older deploy. Refusing is correct: the
        # handshake fails closed and the operator reconnects.
        return None
