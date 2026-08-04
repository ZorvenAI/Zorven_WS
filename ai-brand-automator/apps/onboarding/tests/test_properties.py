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
from django.utils import timezone
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from onboarding.models import BrandAsset

from apps.onboarding.models import (
    TERMINAL_STATUSES,
    MeetingRecording,
    SessionStatus,
)
from apps.onboarding.tests.factories import (
    make_brand_asset,
    make_company,
    make_consent,
    make_question,
    make_recording,
    make_session,
)

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


# ══ B-02 ═════════════════════════════════════════════════════════════


@pytest.mark.django_db
@given(cycles=st.integers(min_value=1, max_value=12))
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_n_start_stop_cycles_produce_n_rows(cycles):
    """AC-1 generalised: the card says three, but nothing is special about 3.

    An operator pausing for a phone call produces however many cycles the
    meeting needed, and each must stay independently addressable.
    """
    session = make_session()
    for index in range(cycles):
        make_recording(session=session, duration_s=index + 1)

    rows = MeetingRecording.objects.filter(session=session)
    assert rows.count() == cycles
    assert {r.session_id for r in rows} == {session.pk}
    assert sorted(r.duration_s for r in rows) == list(range(1, cycles + 1))


@pytest.mark.django_db
@given(tag=st.sampled_from([c[0] for c in BrandAsset.USAGE_TAG_CHOICES]))
@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_every_declared_usage_tag_is_storable(tag):
    """A choice that cannot be stored is a choice that will surprise H-01."""
    asset = make_brand_asset(file_name=f"{tag}.jpg", usage_tag=tag)
    asset.refresh_from_db()
    assert asset.usage_tag == tag


@pytest.mark.django_db
@given(revoked=st.booleans())
@settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_is_active_always_agrees_with_revoked_at(revoked):
    """One expression for consent state, so two consumers cannot disagree."""
    consent = make_consent()
    if revoked:
        consent.revoked_at = timezone.now()
        consent.save(update_fields=["revoked_at"])
        consent.refresh_from_db()

    assert consent.is_active is (not revoked)
    assert consent.is_active is (consent.revoked_at is None)
