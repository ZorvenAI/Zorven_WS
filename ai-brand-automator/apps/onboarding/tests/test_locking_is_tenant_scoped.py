"""Every row re-lock goes through the tenant-scoped queryset.

Four review actions read-modify-write a row and lock it first: session
consent (B-07), provenance confirm and edit (B-06), and recording stop
(B-08). All four originally re-fetched through the model's global manager
after ``get_object()`` had already applied the tenant filter.

That is not a hole while ``get_object()`` runs first — it 404s a cross-tenant
id — but it means the lock and the permission check disagree about which rows
exist, and only the ordering keeps them honest. Reorder the two lines, or add
a fifth action that locks without fetching first, and the disagreement becomes
a cross-tenant write.

Asserted across all four at once, in one file, because the fix is a pattern
rather than four separate bugs: the next action to lock a row should fail here
if it reaches for the global manager.
"""

from __future__ import annotations

import inspect

import pytest

from apps.onboarding import views

pytestmark = pytest.mark.unit

LOCKING_METHODS = [
    (views.OnboardingSessionViewSet, "_grant_consent"),
    (views.FieldProvenanceViewSet, "confirm"),
    (views.FieldProvenanceViewSet, "edit"),
    (views.MeetingRecordingViewSet, "stop"),
]


@pytest.mark.parametrize(
    "viewset,method",
    LOCKING_METHODS,
    ids=[f"{v.__name__}.{m}" for v, m in LOCKING_METHODS],
)
def test_the_lock_uses_the_scoped_queryset(viewset, method):
    # Three independent facts rather than one adjacency match: the method
    # locks, the lock derives from the scoped queryset, and it does not use
    # the global manager.
    #
    # The first version required "self.get_queryset().select_for_update("
    # literally, and broke as soon as a comment appeared mid-chain — the
    # brittleness a source-inspection test earns by asserting on shape
    # instead of substance.
    source = " ".join(inspect.getsource(getattr(viewset, method)).split())

    assert "select_for_update(" in source, "this method no longer locks at all"
    assert (
        "self.get_queryset()" in source
    ), "the lock does not derive from the tenant-scoped queryset"
    assert ".objects.select_for_update(" not in source, (
        "locking through the global manager: the lock and the permission "
        "check would disagree about which rows exist"
    )


def test_no_view_reaches_for_a_global_lock():
    """A blanket check, so a *new* action cannot reintroduce the pattern
    without this file noticing."""
    source = " ".join(inspect.getsource(views).split())
    assert ".objects.select_for_update(" not in source
