"""Property tests for the two B-01 invariants.

The example-based tests check the statuses and combinations we thought of.
These check every pair the state machine admits, and arbitrary score/evidence
shapes, because both invariants are the kind that fail on the case nobody
enumerated.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from apps.onboarding.models import TERMINAL_STATUSES, SessionStatus
from apps.onboarding.tests.factories import make_company, make_question, make_session

pytestmark = [pytest.mark.django_db, pytest.mark.property]

statuses = st.sampled_from([s.value for s in SessionStatus])
terminal = st.sampled_from([s.value for s in TERMINAL_STATUSES])
non_terminal = st.sampled_from(
    [s.value for s in SessionStatus if s not in TERMINAL_STATUSES]
)

# Django's test transaction is per-test, so hypothesis reuses one database
# state across examples; function_scoped_fixture is expected here.
db_settings = settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@given(first=non_terminal, second=non_terminal)
@db_settings
def test_no_pair_of_non_terminal_statuses_permits_two_sessions(first, second):
    """Whichever two the caller picks, the second insert fails."""
    company = make_company()
    make_session(company=company, status=first)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_session(company=company, status=second)


@given(closed=terminal, reopened=non_terminal)
@db_settings
def test_any_terminal_status_releases_the_constraint(closed, reopened):
    """COMPLETED and ARCHIVED both free the company for a new session."""
    company = make_company()
    first = make_session(company=company, status=SessionStatus.DRAFT)
    first.status = closed
    first.save(update_fields=["status"])

    second = make_session(company=company, status=reopened)
    assert second.pk != first.pk


@given(
    score=st.one_of(st.none(), st.floats(min_value=0, max_value=1)),
    spans=st.lists(
        st.fixed_dictionaries(
            {
                "recording_id": st.text(min_size=1, max_size=8),
                "t_start": st.floats(min_value=0, max_value=1000),
                "t_end": st.floats(min_value=0, max_value=1000),
            }
        ),
        max_size=3,
    ),
)
@db_settings
def test_score_and_evidence_are_accepted_only_together(score, spans):
    """OG-06 for every combination: both present, or both absent."""
    both = score is not None and bool(spans)
    neither = score is None and not spans

    if both or neither:
        question = make_question(sufficiency_score=score, evidence=spans)
        assert (question.sufficiency_score is not None) == bool(question.evidence)
    else:
        with pytest.raises(ValidationError):
            make_question(sufficiency_score=score, evidence=spans)


@given(status=statuses)
@db_settings
def test_is_terminal_agrees_with_the_terminal_set(status):
    session = make_session(status=status)
    assert session.is_terminal == (status in {s.value for s in TERMINAL_STATUSES})
