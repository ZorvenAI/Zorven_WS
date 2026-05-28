"""Unit tests for manual rollback manager (US-035, OPT-08)."""

from datetime import datetime, timedelta, timezone

from app.logic.lifecycle import VALID_TRANSITIONS, PromptState
from app.logic.rollback_manager import (
    ARCHIVE_RETENTION_DAYS,
    RollbackResult,
    is_within_retention_window,
)


class TestArchiveRetention:
    """AC-1: Archived versions retained for ≥30 days."""

    def test_retention_days_is_30(self):
        assert ARCHIVE_RETENTION_DAYS == 30

    def test_within_window_recent(self):
        recent = datetime.now(timezone.utc) - timedelta(days=10)
        assert is_within_retention_window(recent) is True

    def test_within_window_at_29_days(self):
        boundary = datetime.now(timezone.utc) - timedelta(days=29, hours=23)
        assert is_within_retention_window(boundary) is True

    def test_just_outside_30_days(self):
        old = datetime.now(timezone.utc) - timedelta(days=30, hours=1)
        assert is_within_retention_window(old) is False

    def test_none_archived_at(self):
        assert is_within_retention_window(None) is True

    def test_custom_retention_days(self):
        recent = datetime.now(timezone.utc) - timedelta(days=5)
        assert is_within_retention_window(recent, retention_days=7) is True
        assert is_within_retention_window(recent, retention_days=3) is False


class TestLifecycleTransitions:
    """ARCHIVED → PRODUCTION transition enabled for rollback."""

    def test_archived_to_production_valid(self):
        allowed = VALID_TRANSITIONS[PromptState.ARCHIVED]
        assert PromptState.PRODUCTION in allowed

    def test_production_to_archived_valid(self):
        allowed = VALID_TRANSITIONS[PromptState.PRODUCTION]
        assert PromptState.ARCHIVED in allowed

    def test_archived_has_outgoing_transition(self):
        allowed = VALID_TRANSITIONS[PromptState.ARCHIVED]
        assert len(allowed) >= 1


class TestRollbackResult:
    def test_default_fields(self):
        r = RollbackResult(
            prompt_name="test-prompt",
            rolled_back_version=5,
            restored_version=3,
        )
        assert r.prompt_name == "test-prompt"
        assert r.rolled_back_version == 5
        assert r.restored_version == 3
        assert r.success is False
        assert r.cache_invalidated is False
        assert r.error == ""

    def test_success_fields(self):
        r = RollbackResult(
            prompt_name="test",
            rolled_back_version=5,
            restored_version=3,
            success=True,
            cache_invalidated=True,
        )
        assert r.success is True
        assert r.cache_invalidated is True

    def test_error_field(self):
        r = RollbackResult(
            prompt_name="test",
            rolled_back_version=0,
            restored_version=3,
            error="Not found",
        )
        assert r.error == "Not found"


class TestRollbackToVersionNoRegistry:
    """rollback_to_version with no MLflow registry."""

    async def test_no_registry_returns_error(self):
        from app.logic.rollback_manager import rollback_to_version

        result = await rollback_to_version(
            prompt_name="test",
            target_version=3,
            mlflow_registry=None,
        )
        assert result.success is False
        assert "not available" in result.error
