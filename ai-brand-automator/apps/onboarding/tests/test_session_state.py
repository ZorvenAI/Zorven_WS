"""B-04 · the §9.4 transition table and the service that enforces it.

AC-2 asks for every legal transition to be asserted "exhaustively rather than
by sampling". That is only achievable because the rules are data: the sweep
below walks all 11 × 11 status pairs and asserts that exactly the declared
edges are legal. Written as ``if`` branches there would be no table to walk.

The table tests need no database — they are assertions about a dict — so they
are kept separate from the ones that do. That is not tidiness: the sweep runs
121 pairs, and 121 round trips to Postgres for a dict lookup would be the
kind of slow property test the CI durations flagged.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.onboarding import state
from apps.onboarding.models import SessionStatus
from apps.onboarding.services.session_state import InvalidTransition, transition
from apps.onboarding.tests.factories import make_session

ALL_STATUSES = [s.value for s in SessionStatus]
statuses = st.sampled_from(ALL_STATUSES)


# ── The table itself · no database needed ────────────────────────────


@pytest.mark.unit
def test_every_key_and_target_is_a_real_status():
    """A typo would silently forbid a legal move rather than fail."""
    assert set(state.TRANSITIONS) == set(ALL_STATUSES)
    for source, targets in state.TRANSITIONS.items():
        unknown = set(targets) - set(ALL_STATUSES)
        assert not unknown, f"{source} points at unknown statuses: {unknown}"


@pytest.mark.unit
def test_terminal_states_have_no_way_out():
    """AC-2's other half: COMPLETED and ARCHIVED are ends, not waypoints."""
    assert state.TRANSITIONS["ARCHIVED"] == frozenset()
    assert state.TRANSITIONS["COMPLETED"] == frozenset({"ARCHIVED"})
    assert state.TERMINAL == {"COMPLETED", "ARCHIVED"}


@pytest.mark.unit
def test_the_processing_failure_edge_returns_to_gathered():
    """§9.4: a failed PROCESSING run must not strand the evidence.

    Sending it to DRAFT would leave a meeting's worth of recordings behind a
    session that looks unstarted.
    """
    assert "GATHERED" in state.TRANSITIONS["PROCESSING"]
    assert "DRAFT" not in state.TRANSITIONS["PROCESSING"]


@pytest.mark.unit
def test_meeting_live_is_re_entrant():
    """§9.4: stopping and restarting a recording must not end the session."""
    assert "MEETING_LIVE" in state.TRANSITIONS["MEETING_LIVE"]


@pytest.mark.unit
def test_escalated_has_no_static_target():
    """Its legal move is a property of the row, not of the status."""
    assert state.TRANSITIONS["ESCALATED"] == frozenset()
    assert state.legal_targets("ESCALATED", "PROCESSING") == {"PROCESSING"}
    # Nowhere legal to go without a recorded origin — guessing is what §9.4
    # says strands a session.
    assert state.legal_targets("ESCALATED", None) == frozenset()


@pytest.mark.unit
@pytest.mark.parametrize("current", ALL_STATUSES)
@pytest.mark.parametrize("target", ALL_STATUSES)
def test_exactly_the_declared_edges_are_legal(current, target):
    """The exhaustive sweep AC-2 asks for: every one of the 11 × 11 pairs.

    Parameterised rather than generated. Hypothesis *samples*, and AC-2 says
    "exhaustively rather than by sampling" — so however well a 200-example
    run happens to cover the space (it did cover all 121 under the repo's
    pinned seed), nothing guarantees it, and a Hypothesis upgrade could
    quietly shrink the coverage while the test kept passing.

    121 cases with no database cost milliseconds, and a failure names the
    exact pair rather than a falsifying example.
    """
    expected = target in state.TRANSITIONS[current]
    assert state.is_legal(current, target) is expected


@pytest.mark.property
@given(origin=st.sampled_from(sorted(state.ESCALATABLE_FROM)), other=statuses)
@settings(max_examples=100, deadline=None)
def test_escalation_only_returns_to_its_origin(origin, other):
    """From ESCALATED, the origin is legal and everything else is not."""
    assert state.is_legal("ESCALATED", origin, origin)
    if other != origin:
        assert not state.is_legal("ESCALATED", other, origin)


# ── The service · these do touch the database ────────────────────────
#
# Marked per test rather than per module: the table tests above must stay
# database-free, which is what keeps the 121-case sweep fast.


@pytest.mark.django_db
@pytest.mark.parametrize(
    "current,target",
    [(c, t) for c, ts in state.TRANSITIONS.items() for t in sorted(ts)],
)
def test_all_legal_transitions(current, target):
    """The card's named case, parameterised over the §9.4 table.

    Every declared edge is exercised against a real row, so the table and the
    service cannot drift apart.
    """
    session = make_session(status=current)
    transition(session, target)

    session.refresh_from_db()
    assert session.status == target


@pytest.mark.django_db
@pytest.mark.parametrize(
    "current,target",
    [
        ("READY", "CONFIRMED"),  # AC-2's worked example: skips the middle
        ("DRAFT", "COMPLETED"),
        ("ARCHIVED", "DRAFT"),
        ("COMPLETED", "MEETING_LIVE"),
        ("PROCESSING", "DRAFT"),  # the failure edge goes to GATHERED
    ],
)
def test_illegal_transitions_raise(current, target):
    session = make_session(status=current)

    with pytest.raises(InvalidTransition) as exc:
        transition(session, target)

    assert exc.value.code == "ERR-18"
    assert exc.value.current == current
    assert target not in exc.value.allowed

    session.refresh_from_db()
    assert session.status == current, "a refused transition still wrote"


@pytest.mark.django_db
def test_escalated_from_roundtrip():
    """The card's named case, and AC-4: escalation returns where it came from.

    Not to the start — a session escalated out of PROCESSING that resumed at
    DRAFT would discard everything the meeting produced.
    """
    session = make_session(status="GATHERED")
    transition(session, "PROCESSING")

    transition(session, "ESCALATED")
    session.refresh_from_db()
    assert session.status == "ESCALATED"
    assert session.escalated_from == "PROCESSING"

    transition(session, "PROCESSING")
    session.refresh_from_db()
    assert session.status == "PROCESSING"
    assert session.escalated_from is None, "the pointer outlived its purpose"


@pytest.mark.django_db
def test_an_escalated_session_cannot_resume_anywhere_else():
    session = make_session(status="READY")
    transition(session, "ESCALATED")

    with pytest.raises(InvalidTransition):
        transition(session, "MEETING_LIVE")

    transition(session, "READY")
    assert session.status == "READY"


@pytest.mark.django_db
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(origin=st.sampled_from(sorted(state.ESCALATABLE_FROM)))
@pytest.mark.property
def test_escalation_round_trips_from_every_escalatable_state(origin):
    """Whichever state escalates, resolution returns to that one."""
    session = make_session(status=origin)
    transition(session, "ESCALATED")
    assert session.escalated_from == origin

    transition(session, origin)
    assert session.status == origin
    assert session.escalated_from is None
