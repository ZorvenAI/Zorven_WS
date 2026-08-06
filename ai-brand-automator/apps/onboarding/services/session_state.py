"""Server-side session transitions (Design §9.4).

§9.4 is explicit that "transitions are server-side only" and happen "through
named service methods" — not by a client writing whatever status it likes.
The API layer therefore never assigns ``session.status`` directly; it calls
``transition`` and lets this module refuse.

The rules themselves live in ``apps.onboarding.state`` as data. This module
is only the enforcement and the bookkeeping around ESCALATED.
"""

from __future__ import annotations

from django.db import transaction

from apps.onboarding import state
from apps.onboarding.errors import INVALID_TRANSITION


class InvalidTransition(Exception):
    """A status change §9.4 does not allow.

    Carries the current status and the legal set because AC-2 requires the
    response body to name both: an operator told only "invalid" has to go and
    read the state diagram, which is precisely the moment they will guess
    instead.
    """

    def __init__(self, current: str, target: str, allowed: frozenset[str]):
        self.current = current
        self.target = target
        self.allowed = sorted(allowed)
        self.code = INVALID_TRANSITION
        super().__init__(
            f"Cannot move a session from {current} to {target}. "
            f"Legal next states: {', '.join(self.allowed) or 'none'}."
        )


@transaction.atomic
def transition(session, target: str, *, save: bool = True):
    """Move *session* to *target*, or raise :class:`InvalidTransition`.

    Entering ESCALATED records where it came from, and leaving clears it.
    That bookkeeping lives here rather than in the caller because §9.4 makes
    the round trip an invariant, and an invariant maintained by every caller
    is one that will eventually be maintained by all but one of them.
    """
    current = session.status
    if not state.is_legal(current, target, session.escalated_from):
        raise InvalidTransition(
            current, target, state.legal_targets(current, session.escalated_from)
        )

    fields = ["status"]
    if target == "ESCALATED":
        session.escalated_from = current
        fields.append("escalated_from")
    elif current == "ESCALATED":
        # Resolution: the row has arrived where escalated_from pointed, so the
        # pointer has done its job and must not linger to confuse a later
        # escalation.
        session.escalated_from = None
        fields.append("escalated_from")

    session.status = target
    if save:
        session.save(update_fields=[*fields, "updated_at"])
    return session
