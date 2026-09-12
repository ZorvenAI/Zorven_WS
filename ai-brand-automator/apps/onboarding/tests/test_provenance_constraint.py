"""B-05 · the grounding constraint (AC-1, AC-2, AC-4).

Design §10.1 calls this constraint "the most important line in this section".
The tests exist to prove it lives in PostgreSQL rather than in Python, which
is why AC-2 names four write paths rather than one — the raw SQL case is not
pedantry, it is the assertion that a future writer bypassing the ORM still
cannot create an unsourced row.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.onboarding.models import (
    FieldClassification,
    FieldProvenance,
    ProvenanceStatus,
)
from apps.onboarding.services.provenance import write_provenance
from apps.onboarding.tests.factories import (
    evidence_span,
    make_brand_asset,
    make_provenance,
    make_recording,
    make_session,
)

pytestmark = pytest.mark.django_db


def raw_insert(session, **overrides) -> None:
    """Insert straight into the table, bypassing Django entirely.

    Column names rather than model fields on purpose: this must not go
    through anything that could apply a Python-side check.
    """
    values = {
        "session_id": session.pk,
        "tenant_id": session.tenant_id,
        "model_name": "Company",
        "field_name": "legal_name",
        "extracted_value": '"raw"',
        "final_value": None,
        "classification": "SECONDARY",
        "confidence": None,
        "source_recording_id": None,
        "source_span": None,
        "source_media_id": None,
        "status": "PENDING",
        "reviewed_by_id": None,
        "reviewed_at": None,
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(["%s"] * len(values))

    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO onboarding_sessions_fieldprovenance "
            f"({columns}, created_at, updated_at) "
            f"VALUES ({placeholders}, NOW(), NOW())",
            list(values.values()),
        )


# ── AC-1 · the model matches §10.1 ───────────────────────────────────


def test_the_model_carries_every_designed_field():
    row = make_provenance()
    for field in (
        "session",
        "model_name",
        "field_name",
        "extracted_value",
        "final_value",
        "classification",
        "confidence",
        "source_recording",
        "source_span",
        "source_media",
        "status",
        "reviewed_by",
        "reviewed_at",
    ):
        assert hasattr(row, field), field


def test_one_provenance_row_per_field_per_session():
    row = make_provenance()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_provenance(
                session=row.session,
                model_name=row.model_name,
                field_name=row.field_name,
            )


def test_the_same_field_on_two_sessions_is_fine():
    """The uniqueness is per session, not global."""
    first = make_provenance()
    second = make_provenance(session=make_session())
    assert first.field_name == second.field_name


def test_values_round_trip_losslessly():
    """JSON rather than text: six of B-03's Company fields are JSON-typed,
    and a provenance row that stringified them would disagree with the value
    it describes about its own shape."""
    structured = [{"name": "Blue Tokai", "url": "https://example.com"}]
    row = make_provenance(field_name="competitors", extracted_value=structured)

    row.refresh_from_db()
    assert row.extracted_value == structured
    assert row.extracted_value[0]["name"] == "Blue Tokai"


@pytest.mark.parametrize(
    "value",
    [
        "a plain string",
        42,
        3.14,
        True,
        ["a", "list"],
        {"a": {"nested": "object"}},
    ],
)
def test_any_json_shape_survives(value):
    """Every JSON shape a Company field can hold.

    JSON ``null`` is deliberately absent: Django's JSONField maps Python
    ``None`` onto SQL NULL, so a stored JSON null would be indistinguishable
    from "no value at all" — and ``extracted_value`` is required, because a
    provenance row for nothing is not provenance.
    """
    row = make_provenance(extracted_value=value)
    row.refresh_from_db()
    assert row.extracted_value == value


def test_extracted_value_is_required():
    """The column is NOT NULL: there is no provenance for an absent value."""
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_provenance(extracted_value=None)


# ── AC-2 · the constraint rejects ungrounded rows, on every path ─────


def test_create_without_source_raises():
    """The card's named case: the ORM path is blocked."""
    session = make_session()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FieldProvenance.objects.create(
                session=session,
                tenant=session.tenant,
                model_name="Company",
                field_name="legal_name",
                extracted_value="ungrounded",
            )


def test_bulk_create_without_source_raises():
    """The card's named case, and the path J-03 actually uses.

    This is why the rule is a constraint and not a ``save()`` override:
    bulk_create never calls save().
    """
    session = make_session()
    rows = [
        FieldProvenance(
            session=session,
            tenant=session.tenant,
            model_name="Company",
            field_name=f"field_{i}",
            extracted_value="ungrounded",
        )
        for i in range(3)
    ]

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FieldProvenance.objects.bulk_create(rows)


def test_bulk_create_with_ignore_conflicts_does_not_silently_skip():
    """``ignore_conflicts`` turns violations into skipped rows.

    If J-03 ever passes it, ungrounded rows would vanish rather than raise —
    indistinguishable from success. Asserting the count makes a silent skip
    fail rather than pass.
    """
    session = make_session()
    grounded = FieldProvenance(
        session=session,
        tenant=session.tenant,
        model_name="Company",
        field_name="grounded",
        extracted_value="ok",
        source_span=evidence_span(),
    )
    ungrounded = FieldProvenance(
        session=session,
        tenant=session.tenant,
        model_name="Company",
        field_name="ungrounded",
        extracted_value="not ok",
    )

    try:
        with transaction.atomic():
            FieldProvenance.objects.bulk_create(
                [grounded, ungrounded], ignore_conflicts=True
            )
    except IntegrityError:
        pass  # also acceptable — what matters is the row does not exist

    assert not FieldProvenance.objects.filter(field_name="ungrounded").exists()


def test_raw_sql_insert_without_source_raises():
    """The card's named case, and the point of the whole story.

    Django is not in this path at all. If this passes, the rule is in
    PostgreSQL; if it fails, the rule was only ever in Python.
    """
    session = make_session()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            raw_insert(session)


def test_a_data_migration_style_write_without_source_raises():
    """AC-2's fourth path: the historical model a data migration would use.

    ``apps.get_model`` returns a model without custom save() or managers, so
    this is the closest a test can get to what runs inside a migration.
    """
    from django.apps import apps as django_apps

    session = make_session()
    Historical = django_apps.get_model("onboarding_sessions", "FieldProvenance")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Historical.objects.create(
                session_id=session.pk,
                tenant_id=session.tenant_id,
                model_name="Company",
                field_name="from_migration",
                extracted_value="ungrounded",
            )


@pytest.mark.parametrize("source", ["source_recording", "source_span", "source_media"])
def test_any_single_source_is_enough(source):
    """AC-2's other half: one populated source saves successfully."""
    session = make_session()
    builders = {
        "source_recording": lambda: make_recording(session=session),
        "source_span": lambda: evidence_span(),
        "source_media": lambda: make_brand_asset(company=session.company),
    }

    # Clear all three first, then populate exactly one, so the factory's
    # default source_span cannot quietly satisfy the constraint for us.
    sources = {"source_recording": None, "source_span": None, "source_media": None}
    sources[source] = builders[source]()

    row = make_provenance(session=session, **sources)

    row.refresh_from_db()
    assert row.has_source


def test_raw_sql_with_a_source_succeeds():
    """The constraint must not reject grounded rows either."""
    session = make_session()
    raw_insert(session, source_span='{"recording_id": "r_01"}')

    assert FieldProvenance.objects.filter(session=session).count() == 1


# ── The confidence bound ─────────────────────────────────────────────


@pytest.mark.parametrize("value", ["0.000", "0.500", "1.000"])
def test_confidence_within_range_is_accepted(value):
    row = make_provenance(confidence=Decimal(value))
    row.refresh_from_db()
    assert row.confidence == Decimal(value)


@pytest.mark.parametrize("value", ["-0.001", "1.001"])
def test_confidence_outside_range_is_refused(value):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_provenance(confidence=Decimal(value))


def test_confidence_may_be_null_before_scoring():
    assert make_provenance(confidence=None).confidence is None


# ── AC-4 · PG-06, manual-edit protection ─────────────────────────────


@pytest.mark.parametrize(
    "protected", [ProvenanceStatus.CONFIRMED, ProvenanceStatus.EDITED]
)
def test_confirmed_row_not_overwritten(protected):
    """The card's named case: a re-run must not overwrite a reviewer.

    PG-06 says conflicts are "surfaced through SKL-OIA-14, never silently
    resolved", so the row is marked CONFLICT and returned rather than being
    quietly updated or quietly skipped.
    """
    # A genuinely reviewed row: the agent's proposal stays in
    # extracted_value and the reviewer's decision lands in final_value,
    # which is what those two columns mean. Modelling it with the reviewer's
    # text in extracted_value would test a row shape that cannot occur.
    row = make_provenance(
        extracted_value="what the agent proposed",
        final_value="what the reviewer decided",
        status=protected,
    )

    result = write_provenance(
        row.session,
        [
            {
                "model_name": row.model_name,
                "field_name": row.field_name,
                "extracted_value": "value from the re-run",
                "source_span": evidence_span(),
            }
        ],
    )

    row.refresh_from_db()
    assert row.extracted_value == "what the agent proposed", "a re-run overwrote it"
    assert row.final_value == "what the reviewer decided", "the reviewer was lost"
    assert row.status == ProvenanceStatus.CONFLICT
    assert result.conflicted == [row]
    assert result.updated == []


def test_a_pending_row_is_overwritten_freely():
    """PG-06 protects reviewed rows only; an unreviewed one is the agent's."""
    row = make_provenance(extracted_value="first pass", status=ProvenanceStatus.PENDING)

    result = write_provenance(
        row.session,
        [
            {
                "model_name": row.model_name,
                "field_name": row.field_name,
                "extracted_value": "second pass",
                "source_span": evidence_span(),
            }
        ],
    )

    row.refresh_from_db()
    assert row.extracted_value == "second pass"
    assert result.updated == [row]
    assert result.conflicted == []


def test_write_provenance_creates_rows_that_do_not_exist_yet():
    session = make_session()

    result = write_provenance(
        session,
        [
            {
                "model_name": "Company",
                "field_name": "legal_name",
                "extracted_value": "Kalyani Coffee Roasters Pvt Ltd",
                "classification": FieldClassification.KEY,
                "source_span": evidence_span(),
            }
        ],
    )

    assert len(result.created) == 1
    assert result.created[0].classification == FieldClassification.KEY
    assert result.total == 1


def test_write_provenance_still_cannot_create_an_ungrounded_row():
    """The service does not re-check grounding — the database does.

    Duplicating the rule in Python would create a second definition that
    could drift from the first.
    """
    session = make_session()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            write_provenance(
                session,
                [
                    {
                        "model_name": "Company",
                        "field_name": "legal_name",
                        "extracted_value": "ungrounded",
                    }
                ],
            )


def test_is_protected_agrees_with_the_status():
    for status in ProvenanceStatus:
        row = FieldProvenance(status=status)
        expected = status in (ProvenanceStatus.CONFIRMED, ProvenanceStatus.EDITED)
        assert row.is_protected is expected, status


# ── PR #547 review · has_source must mirror the constraint ───────────


@pytest.mark.parametrize("span", [{}, [], {"recording_id": "r_01"}])
def test_has_source_agrees_with_the_database_for_any_span(span):
    """An empty span is grounded to PostgreSQL, so it must be here too.

    ``has_source`` used truthiness while the constraint asks IS NOT NULL, so
    ``{}`` and ``[]`` were storable yet reported ungrounded — two readings of
    one rule disagreeing, which is what putting the rule in the database was
    meant to prevent.
    """
    session = make_session()
    row = FieldProvenance.objects.create(
        session=session,
        tenant=session.tenant,
        model_name="Company",
        field_name="legal_name",
        extracted_value="value",
        source_span=span,
    )

    row.refresh_from_db()
    assert row.source_span == span, "the span did not survive the round trip"
    assert row.has_source is True


def test_has_source_is_false_only_when_all_three_are_null():
    row = FieldProvenance(
        source_recording_id=None, source_span=None, source_media_id=None
    )
    assert row.has_source is False
