"""The §9.4 session state machine, as data.

The card is blunt about why this is a table rather than a chain of ``if``
branches: written as branches "it cannot be exhaustively tested and it will
drift from Design §9.4 within two sprints." As a dict, a property test can
sweep all 11 × 11 status pairs and assert that exactly the declared edges are
legal — which is what AC-2 means by "exhaustively rather than by sampling".

Deliberately free of Django imports. The table is the contract; keeping it
importable without an app registry means it can be tested, diffed and read on
its own.

§9.4's edges live in a figure rather than in prose, so this table was derived
from the eleven statuses plus the invariants the section states in text, and
confirmed against the figure by the maintainer on 2026-08-05. Four of those
invariants are load-bearing and are marked at their edges below.
"""

from __future__ import annotations

#: Allowed transitions, ``{from_status: frozenset(to_status, ...)}``.
#:
#: Every key and every target must be a member of ``SessionStatus``; a test
#: asserts that, so a typo here fails loudly rather than silently forbidding
#: a legal move.
TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"PREPARING", "ARCHIVED"}),
    "PREPARING": frozenset({"READY", "DRAFT", "ESCALATED"}),
    "READY": frozenset({"MEETING_LIVE", "ESCALATED"}),
    # MEETING_LIVE is re-entrant (§9.4): the brand owner takes a phone call,
    # the operator stops and restarts, and that must not end the session.
    "MEETING_LIVE": frozenset({"MEETING_LIVE", "GATHERED", "ESCALATED"}),
    "GATHERED": frozenset({"PROCESSING", "MEETING_LIVE", "ESCALATED"}),
    # The failure edge returns to GATHERED, never DRAFT (§9.4). Evidence —
    # recordings, transcripts, media — survives a failed PROCESSING run; only
    # the FieldProvenance rows that run wrote are rolled back. Sending it to
    # DRAFT would strand a meeting's worth of evidence behind a session that
    # looks unstarted.
    "PROCESSING": frozenset({"REVIEW_PENDING", "GATHERED", "ESCALATED"}),
    # PROCESSING is the re-run edge (J-01 AC-4): operator re-processes after
    # reviewing or confirming, e.g. after adding more evidence.
    "REVIEW_PENDING": frozenset({"CONFIRMED", "PROCESSING", "ESCALATED"}),
    "CONFIRMED": frozenset({"COMPLETED", "PROCESSING", "ESCALATED"}),
    "COMPLETED": frozenset({"ARCHIVED"}),
    # ESCALATED has no static targets: resolution restores escalated_from,
    # so its legal move depends on the row rather than the table. See
    # ``legal_targets``.
    "ESCALATED": frozenset(),
    "ARCHIVED": frozenset(),
}

#: Statuses a session can never leave.
TERMINAL = frozenset({"COMPLETED", "ARCHIVED"})

#: The status ESCALATED can be entered from. Kept separate from TRANSITIONS
#: so "which states may escalate" is answerable without scanning every row.
ESCALATABLE_FROM = frozenset(
    source for source, targets in TRANSITIONS.items() if "ESCALATED" in targets
)


def legal_targets(current: str, escalated_from: str | None = None) -> frozenset[str]:
    """Statuses reachable from *current*.

    ``escalated_from`` matters only for ESCALATED, whose single legal move is
    back to wherever it came from. Encoding that in TRANSITIONS is impossible
    — the answer is a property of the row, not of the status — so it is
    resolved here, in the one place callers already ask.

    An ESCALATED session with no ``escalated_from`` has nowhere legal to go.
    That is deliberate: guessing a destination is exactly what §9.4 says
    strands a session.
    """
    if current == "ESCALATED":
        return frozenset({escalated_from}) if escalated_from else frozenset()
    return TRANSITIONS.get(current, frozenset())


def is_legal(current: str, target: str, escalated_from: str | None = None) -> bool:
    """True when *current* → *target* is a declared edge."""
    return target in legal_targets(current, escalated_from)
