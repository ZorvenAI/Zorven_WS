"""E2E tests for canary regression and rollback flows (US-060).

Exercises: canary metrics -> regression detection -> auto-rollback,
manual rollback to archived version, retention window enforcement.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.logic.canary_manager import CANARY_STATE_KEY
from app.logic.lifecycle import PromptState
from app.logic.rollback_manager import (
    is_within_retention_window,
    rollback_to_version,
)


@pytest.mark.e2e
class TestCanaryRollback:
    """Canary regression detection and rollback flows."""

    async def test_canary_no_regression_returns_none(self, e2e_canary, e2e_prompt_name):
        """Good canary metrics — check returns None."""
        name = e2e_prompt_name("canary-good")

        await e2e_canary.start_canary(
            name, canary_version=2, production_version=1, agent_code="bpa"
        )

        # Canary scores higher than production
        await e2e_canary.record_canary_metric(name, 1, "json_compliance", 0.80)
        await e2e_canary.record_canary_metric(name, 1, "brand_voice", 0.75)
        await e2e_canary.record_canary_metric(name, 2, "json_compliance", 0.88)
        await e2e_canary.record_canary_metric(name, 2, "brand_voice", 0.82)

        regression = await e2e_canary.check_canary_regression(name)
        assert regression is None

    async def test_canary_regression_detected(
        self, e2e_canary, e2e_cache, e2e_prompt_name
    ):
        """Canary 10% below production (>5% threshold) — regression returned."""
        name = e2e_prompt_name("canary-regress")

        await e2e_canary.start_canary(
            name, canary_version=2, production_version=1, agent_code="cga"
        )

        # Production scores high, canary scores low (>5% regression)
        await e2e_canary.record_canary_metric(name, 1, "json_compliance", 0.90)
        await e2e_canary.record_canary_metric(name, 1, "brand_voice", 0.85)
        await e2e_canary.record_canary_metric(name, 2, "json_compliance", 0.75)
        await e2e_canary.record_canary_metric(name, 2, "brand_voice", 0.70)

        regression = await e2e_canary.check_canary_regression(name)
        assert regression is not None
        assert regression > 0.05

    async def test_canary_rollback_clears_redis_state(
        self, e2e_canary, e2e_cache, e2e_prompt_name
    ):
        """Rollback clears prompt:canary:{name} from Redis."""
        name = e2e_prompt_name("canary-clear")

        await e2e_canary.start_canary(
            name, canary_version=2, production_version=1, agent_code="mra"
        )

        # Verify canary state exists
        state = await e2e_canary.get_canary_state(name)
        assert state is not None

        # Rollback
        result = await e2e_canary.rollback_canary(name)
        assert result is True

        # Verify canary state cleared
        r = await e2e_cache.connect()
        key = CANARY_STATE_KEY.format(name=name)
        exists = await r.exists(key)
        assert exists == 0

    async def test_rollback_to_archived_version(
        self, e2e_registry, e2e_lifecycle, e2e_cache, e2e_prompt_name
    ):
        """v1 PROD->ARCHIVED, v2 PROD, rollback to v1, verify cache invalidated."""
        name = e2e_prompt_name("rollback-archive")

        # Register v1 as PRODUCTION
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

        # Set cache to verify invalidation
        await e2e_cache.set_prompt(name, "cached-v2", ttl=300)

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

    def test_rollback_outside_retention_window_fails(self):
        """31-day-old version outside retention window."""
        archived_at = datetime.now(timezone.utc) - timedelta(days=31)
        assert is_within_retention_window(archived_at) is False

        # Within window
        recent = datetime.now(timezone.utc) - timedelta(days=15)
        assert is_within_retention_window(recent) is True
