"""AC-3 — the migration is additive and reverses cleanly (NFR-COMPAT).

"Reversible" is only worth asserting on a database that has rows in it. An
empty rollback proves the operations are declared reversible; a populated one
proves nothing depends on data the reverse cannot handle.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.onboarding.models import SessionStatus
from apps.onboarding.tests.factories import (
    make_question,
    make_questionnaire,
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


def test_migration_reversible():
    """Forward, populate, backward, forward — no residue."""
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
    assert len(rebuilt) == 3, rebuilt


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
