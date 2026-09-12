"""AC-3 — the migration is additive and reverses cleanly (NFR-COMPAT).

"Reversible" is only worth asserting on a database that has rows in it. An
empty rollback proves the operations are declared reversible; a populated one
proves nothing depends on data the reverse cannot handle.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from apps.onboarding.models import FieldProvenance, SessionStatus
from apps.onboarding.tests.factories import (
    make_company,
    make_consent,
    make_provenance,
    make_question,
    make_questionnaire,
    make_recording,
    make_session,
)

pytestmark = pytest.mark.django_db(transaction=True)

APP_LABEL = "onboarding_sessions"


def migrate_to(target: str | None) -> None:
    """Run the executor to a named migration, or to zero when None."""
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    state = [(APP_LABEL, target)] if target else [(APP_LABEL, None)]
    executor.migrate(state)
    executor.loader.build_graph()


def latest_migration() -> str:
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    nodes = [n for n in executor.loader.graph.nodes if n[0] == APP_LABEL]
    assert nodes, "no migrations found for the app"
    return sorted(nodes)[-1][1]


def restore_all_migrations() -> None:
    """Re-apply every app to its leaf migration.

    ``migrate_to(None)`` unapplies more than this app: ``onboarding.0013``
    adds a FK *to* this app and so depends on it, and every later onboarding
    migration follows 0013. Restoring only ``APP_LABEL`` therefore leaves the
    ``onboarding`` app short of columns the ORM still expects, and the next
    test to create a Company dies on a missing column — which is exactly how
    B-03 surfaced this.

    The database is shared across the module, so a test that tears down
    schema has to put all of it back, not just the part it was inspecting.
    """
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())
    executor.loader.build_graph()


def expected_tables() -> list[str]:
    """Every table this app's models declare, from the models themselves.

    Was a hardcoded list of six. That list rots on every story that adds a
    model — B-08 and C-02 both hit it — and the failure reads as "migrations
    are broken" when the truth is "the snapshot is stale", which is the worst
    kind of red because it trains you to update the expectation without
    reading it.

    Deriving it is not weaker. The assertion is still that migrating to zero
    and back rebuilds a table for **exactly** the declared models: a model
    whose migration was forgotten is missing from `rebuilt`, and a table left
    behind by a deleted model is present and unexpected. Both still fail.
    """
    from django.apps import apps as django_apps

    return sorted(
        model._meta.db_table
        for model in django_apps.get_app_config(APP_LABEL).get_models()
    )


def test_migration_reversible():
    """Forward, populate, backward, forward — no residue."""
    try:
        head = latest_migration()

        session = make_session(status=SessionStatus.MEETING_LIVE)
        questionnaire = make_questionnaire(company=session.company, session=session)
        make_question(questionnaire=questionnaire, order=1)

        # Backwards on a populated database.
        migrate_to(None)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE %s",
                [f"{APP_LABEL}_%"],
            )
            remaining = [row[0] for row in cursor.fetchall()]
        assert remaining == [], f"tables survived the reverse: {remaining}"

        # And forward again, so the migration is not one-shot.
        migrate_to(head)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE %s",
                [f"{APP_LABEL}_%"],
            )
            rebuilt = sorted(row[0] for row in cursor.fetchall())

        # Named rather than counted: a bare count silently passes when a table is
        # swapped for another, and has to be edited by every story that adds one.
        assert rebuilt == expected_tables(), rebuilt
    finally:
        # This test unapplies migrations other apps depend on.
        restore_all_migrations()


def test_the_partial_index_exists_in_the_database():
    """AC-2 is a database property, so assert it against the database."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
            ["unique_active_session_per_company"],
        )
        row = cursor.fetchone()

    assert row is not None, "the partial unique index was not created"
    definition = row[0].upper()
    assert "UNIQUE" in definition
    assert "WHERE" in definition, "the index is not partial"
    assert "COMPLETED" in definition and "ARCHIVED" in definition


def test_no_existing_table_was_altered():
    """NFR-COMPAT: the migration touches only this app's own tables."""
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(connection)
    for (app_label, _name), migration in loader.disk_migrations.items():
        if app_label != APP_LABEL:
            continue
        for operation in migration.operations:
            model = getattr(operation, "model_name", None) or getattr(
                operation, "name", ""
            )
            assert (
                "company" not in str(model).lower() or "session" in str(model).lower()
            ), f"operation touches an existing model: {operation}"


# ══ B-02 · the BrandAsset extension is additive (AC-4) ═══════════════


def test_brandasset_columns_exist_and_are_nullable():
    """AC-4 is a database property, so assert it against the database.

    A column added NOT NULL without a default is exactly the migration that
    passes on an empty test database and fails on a populated production one.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'onboarding_brandasset' "
            "AND column_name IN %s",
            [("usage_tag", "onboarding_session_id", "ocr_text", "ocr_confidence")],
        )
        columns = dict(cursor.fetchall())

    assert set(columns) == {
        "usage_tag",
        "onboarding_session_id",
        "ocr_text",
        "ocr_confidence",
    }, columns
    for name, nullable in columns.items():
        assert nullable == "YES", f"{name} is NOT NULL — existing rows would fail"


def test_a_row_written_the_old_way_still_inserts():
    """The pre-B-02 insert statement, run verbatim against the new schema."""
    company = make_company()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO onboarding_brandasset "
            "(company_id, file_name, file_type, file_size, gcs_path, "
            " gcs_bucket, uploaded_at, processed, pipeline_status, "
            " pipeline_error, summary, rag_excluded) "
            "VALUES (%s, 'legacy.jpg', 'image', 512, '_raw/legacy.jpg', "
            "'zorven-raw-assets', NOW(), false, 'pending', '', '', false) "
            "RETURNING usage_tag, onboarding_session_id, ocr_text, "
            "ocr_confidence",
            [company.pk],
        )
        row = cursor.fetchone()

    assert row == (None, None, None, None), f"new columns not defaulted null: {row}"


def test_the_b02_migration_reverses_on_populated_data():
    """Forward, populate, backward, forward — with recordings and consent."""
    try:
        head = latest_migration()

        session = make_session(status=SessionStatus.MEETING_LIVE)
        make_recording(session=session, duration_s=42)
        make_consent(session=session)

        migrate_to(None)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE %s",
                [f"{APP_LABEL}_%"],
            )
            assert [r[0] for r in cursor.fetchall()] == []

        migrate_to(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE %s",
                [f"{APP_LABEL}_%"],
            )
            rebuilt = sorted(r[0] for r in cursor.fetchall())

        assert rebuilt == expected_tables(), rebuilt
    finally:
        # This test unapplies migrations other apps depend on.
        restore_all_migrations()


# ══ B-05 · the grounding constraint survives replay (AC-3) ═══════════


def test_the_grounding_constraint_exists_in_the_database():
    """The whole point of B-05: the rule is in PostgreSQL, not in Python."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint " "WHERE conname = %s",
            ["provenance_requires_a_source"],
        )
        row = cursor.fetchone()

    assert row is not None, "the check constraint was not created"
    definition = row[0].lower()
    assert definition.startswith("check")
    for column in ("source_recording_id", "source_span", "source_media_id"):
        assert column in definition, f"{column} missing from the constraint"


def test_the_confidence_bound_exists_in_the_database():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint " "WHERE conname = %s",
            ["confidence_between_zero_and_one"],
        )
        row = cursor.fetchone()

    assert row is not None, "the confidence bound was not created"
    assert "confidence" in row[0].lower()


def test_constraint_replay():
    """The card's named case: reverse and re-apply is clean.

    Asserted with provenance rows present, because an empty replay only
    proves the operations are declared reversible. A populated one proves
    nothing depends on data the reverse cannot handle, and that no surviving
    row violates the constraint when it comes back.
    """
    try:
        head = latest_migration()

        session = make_session(status=SessionStatus.GATHERED)
        make_provenance(session=session, field_name="legal_name")
        make_provenance(session=session, field_name="founder_story")
        assert FieldProvenance.objects.count() == 2

        migrate_to(None)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM pg_constraint WHERE conname = %s",
                ["provenance_requires_a_source"],
            )
            assert cursor.fetchone()[0] == 0, "the constraint survived the reverse"

        migrate_to(head)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM pg_constraint WHERE conname = %s",
                ["provenance_requires_a_source"],
            )
            assert cursor.fetchone()[0] == 1, "the constraint did not come back"

        # And it still bites after the round trip.
        rebuilt = make_session(status=SessionStatus.GATHERED)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                FieldProvenance.objects.create(
                    session=rebuilt,
                    tenant=rebuilt.tenant,
                    model_name="Company",
                    field_name="ungrounded",
                    extracted_value="no source",
                )
    finally:
        restore_all_migrations()
