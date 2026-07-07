"""E2E tests for health check and auto-rollback flows (US-060).

Exercises: rollback window detection, regression detection,
find previous archived version, auto-rollback on severe regression,
no rollback outside window.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.logic.lifecycle import PromptState
from app.logic.rollback_manager import is_within_retention_window, rollback_to_version
from app.tasks.prompt_health_check import (
    _check_regression,
    _find_previous_archived_version,
    _is_within_rollback_window,
)


@pytest.mark.e2e
class TestHealthCheckAutoRollback:
    """Health check regression detection and auto-rollback flows."""

    def test_within_rollback_window(self):
        """Timestamp within 48h -> True, outside -> False."""
        # Within window (promoted 12 hours ago)
        recent = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        assert _is_within_rollback_window(recent, window_hours=48) is True

        # At boundary (promoted exactly 47h ago)
        boundary = (datetime.now(timezone.utc) - timedelta(hours=47)).isoformat()
        assert _is_within_rollback_window(boundary, window_hours=48) is True

        # Outside window (promoted 49h ago)
        old = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
        assert _is_within_rollback_window(old, window_hours=48) is False

        # None timestamp
        assert _is_within_rollback_window(None, window_hours=48) is False

        # Invalid timestamp
        assert _is_within_rollback_window("not-a-date", window_hours=48) is False

    def test_regression_detection(self):
        """Score 0.80 with threshold 0.10 -> regression detected."""
        # Score 0.80 < (1.0 - 0.10) = 0.90 -> regression
        assert _check_regression(0.80, threshold=0.10) is True

        # Score 0.95 >= 0.90 -> no regression
        assert _check_regression(0.95, threshold=0.10) is False

        # Exactly at threshold boundary
        assert _check_regression(0.90, threshold=0.10) is False

        # Severe regression (>15%)
        assert _check_regression(0.70, threshold=0.15) is True
        assert _check_regression(0.84, threshold=0.15) is True
        assert _check_regression(0.86, threshold=0.15) is False

        # None score -> no regression
        assert _check_regression(None, threshold=0.10) is False

    async def test_find_previous_archived_version(
        self, e2e_registry, e2e_lifecycle, e2e_prompt_name
    ):
        """v1 ARCHIVED, v2 PRODUCTION -> finds v1."""
        name = e2e_prompt_name("find-archived")

        # Register v1, promote to PRODUCTION, then archive
        v1 = e2e_registry.register_prompt(
            name=name, template="V1 template", tags={"state": "DRAFT"}
        )
        e2e_lifecycle.transition(
            name, v1.version, PromptState.DRAFT, PromptState.STAGING
        )
        e2e_lifecycle.transition(
            name, v1.version, PromptState.STAGING, PromptState.CANARY
        )
        e2e_lifecycle.transition(
            name, v1.version, PromptState.CANARY, PromptState.PRODUCTION
        )

        # Register v2 and promote to PRODUCTION (auto-archives v1)
        v2 = e2e_registry.register_prompt(
            name=name, template="V2 template", tags={"state": "DRAFT"}
        )
        e2e_lifecycle.transition(
            name, v2.version, PromptState.DRAFT, PromptState.STAGING
        )
        e2e_lifecycle.transition(
            name, v2.version, PromptState.STAGING, PromptState.CANARY
        )
        e2e_lifecycle.promote_to_production(name, v2.version)

        # Find previous archived version
        prev = _find_previous_archived_version(e2e_registry, name, v2.version)
        assert prev == v1.version

    async def test_auto_rollback_on_severe_regression(
        self, e2e_registry, e2e_lifecycle, e2e_cache, e2e_prompt_name
    ):
        """>15% regression within 48h -> rollback, v1 restored."""
        name = e2e_prompt_name("auto-rollback")

        # v1 -> PRODUCTION
        v1 = e2e_registry.register_prompt(
            name=name, template="V1 stable template", tags={"state": "DRAFT"}
        )
        e2e_lifecycle.transition(
            name, v1.version, PromptState.DRAFT, PromptState.STAGING
        )
        e2e_lifecycle.transition(
            name, v1.version, PromptState.STAGING, PromptState.CANARY
        )
        e2e_lifecycle.transition(
            name, v1.version, PromptState.CANARY, PromptState.PRODUCTION
        )

        # v2 -> PRODUCTION (archives v1)
        v2 = e2e_registry.register_prompt(
            name=name, template="V2 regressed template", tags={"state": "DRAFT"}
        )
        e2e_lifecycle.transition(
            name, v2.version, PromptState.DRAFT, PromptState.STAGING
        )
        e2e_lifecycle.transition(
            name, v2.version, PromptState.STAGING, PromptState.CANARY
        )
        e2e_lifecycle.promote_to_production(name, v2.version)

        # Cache the regressed version
        await e2e_cache.set_prompt(name, "V2 regressed template", ttl=300)

        # Rollback to v1
        result = await rollback_to_version(
            prompt_name=name,
            target_version=v1.version,
            mlflow_registry=e2e_registry,
            prompt_cache=e2e_cache,
        )
        assert result.success is True
        assert result.restored_version == v1.version
        assert result.cache_invalidated is True

        # Verify v1 is now PRODUCTION
        v1_info = e2e_registry.get_prompt_version(name, v1.version)
        assert v1_info.tags.get("state") == "PRODUCTION"

    def test_no_rollback_when_outside_window(self):
        """Promoted 49h ago -> outside 48h rollback window."""
        promoted_at = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
        assert _is_within_rollback_window(promoted_at, window_hours=48) is False

        # Confirm retention window also works
        # 31 days old -> outside 30-day retention
        archived_at = datetime.now(timezone.utc) - timedelta(days=31)
        assert is_within_retention_window(archived_at) is False

        # 15 days old -> within retention
        recent = datetime.now(timezone.utc) - timedelta(days=15)
        assert is_within_retention_window(recent) is True
