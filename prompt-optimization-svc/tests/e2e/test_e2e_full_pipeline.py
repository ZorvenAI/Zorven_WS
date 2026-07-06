"""E2E tests for the full optimization pipeline happy path (US-060).

Exercises: register -> lifecycle -> dataset -> guardrails -> validate
-> canary -> promote -> cache invalidate -> agent loads.
"""

import pytest

from app.logic.candidate_validator import split_holdout, validate_candidate
from app.logic.guardrails import run_pre_optimization_guardrails
from app.logic.lifecycle import PromptState


@pytest.mark.e2e
class TestFullPipelineHappyPath:
    """End-to-end pipeline happy path."""

    async def test_register_prompt_in_mlflow(self, e2e_registry, e2e_prompt_name):
        """Register a prompt, verify it exists with DRAFT state."""
        name = e2e_prompt_name("register")
        info = e2e_registry.register_prompt(
            name=name,
            template="You are a helpful assistant for {{context.brand_name}}.",
            tags={"state": "DRAFT", "agent_code": "mra"},
        )
        assert info is not None
        assert info.name == name
        assert info.version >= 1

        retrieved = e2e_registry.get_prompt(name)
        assert retrieved is not None
        assert retrieved.tags.get("state") == "DRAFT"

    async def test_lifecycle_draft_to_staging(
        self, e2e_registry, e2e_lifecycle, e2e_prompt_name
    ):
        """Transition DRAFT -> STAGING, verify state tag updated."""
        name = e2e_prompt_name("staging")
        info = e2e_registry.register_prompt(
            name=name,
            template="Draft template.",
            tags={"state": "DRAFT"},
        )

        result = e2e_lifecycle.transition(
            name, info.version, PromptState.DRAFT, PromptState.STAGING
        )
        assert result is True

        updated = e2e_registry.get_prompt(name)
        assert updated.tags.get("state") == "STAGING"

    def test_dataset_load_and_holdout_split(self, minimal_golden_examples):
        """Load examples, validate size, split, verify deterministic."""
        examples = minimal_golden_examples
        assert len(examples) == 5

        train, holdout = split_holdout(examples, holdout_pct=0.2, seed=42)
        assert len(train) + len(holdout) == len(examples)
        assert len(holdout) >= 1

        # Deterministic — same seed gives same split
        train2, holdout2 = split_holdout(examples, holdout_pct=0.2, seed=42)
        assert train == train2
        assert holdout == holdout2

    async def test_pre_optimization_guardrails_pass(
        self, e2e_cache, minimal_golden_examples, e2e_prompt_name
    ):
        """OPT-01 + OPT-07 pass, lock acquired and released."""
        group = e2e_prompt_name("guard-group")
        owner = "e2e-worker-1"

        result = await run_pre_optimization_guardrails(
            examples=minimal_golden_examples,
            min_dataset_size=3,
            cache_manager=e2e_cache,
            optimization_group=group,
            lock_owner=owner,
        )
        assert result.all_passed is True
        assert len(result.results) == 2
        assert result.results[0].guardrail_id == "OPT-01"
        assert result.results[1].guardrail_id == "OPT-07"

        # Cleanup: release lock
        await e2e_cache.release_optimization_lock(group, owner)

    def test_candidate_validation_canary_decision(self):
        """>5% improvement, no regression >3%, expect CANARY."""
        candidate_scores = {
            "json_compliance": 0.92,
            "brand_voice": 0.88,
            "pii_safety": 0.95,
        }
        production_scores = {
            "json_compliance": 0.85,
            "brand_voice": 0.82,
            "pii_safety": 0.90,
        }

        result = validate_candidate(
            candidate_scores,
            production_scores,
            improvement_threshold=0.05,
            regression_threshold=0.03,
        )
        assert result.passed is True
        assert result.decision == "CANARY"
        assert result.aggregate_improvement > 0.05

    async def test_canary_start_and_metrics(self, e2e_canary, e2e_prompt_name):
        """Start canary, record metrics, check no regression."""
        name = e2e_prompt_name("canary-happy")

        state = await e2e_canary.start_canary(
            prompt_name=name,
            canary_version=2,
            production_version=1,
            agent_code="mra",
        )
        assert state.active is True
        assert state.canary_version == 2
        assert state.production_version == 1

        # Record good metrics for both versions
        await e2e_canary.record_canary_metric(name, 1, "json_compliance", 0.85)
        await e2e_canary.record_canary_metric(name, 2, "json_compliance", 0.90)

        regression = await e2e_canary.check_canary_regression(name)
        assert regression is None  # No regression — canary is better

    async def test_promote_to_production_archives_old(
        self, e2e_registry, e2e_lifecycle, e2e_prompt_name
    ):
        """Promote CANARY->PRODUCTION, verify old PRODUCTION is archived."""
        name = e2e_prompt_name("promote")

        # Register and transition to PRODUCTION (v1)
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

        # Register v2 and advance to CANARY
        v2 = e2e_registry.register_prompt(
            name=name, template="V2 template", tags={"state": "DRAFT"}
        )
        e2e_lifecycle.transition(
            name, v2.version, PromptState.DRAFT, PromptState.STAGING
        )
        e2e_lifecycle.transition(
            name, v2.version, PromptState.STAGING, PromptState.CANARY
        )

        # Promote v2 — should archive v1
        result = e2e_lifecycle.promote_to_production(name, v2.version)
        assert result is True

        # Verify v1 is ARCHIVED
        v1_info = e2e_registry.get_prompt_version(name, v1.version)
        assert v1_info.tags.get("state") == "ARCHIVED"

        # Verify v2 is PRODUCTION
        v2_info = e2e_registry.get_prompt_version(name, v2.version)
        assert v2_info.tags.get("state") == "PRODUCTION"

    async def test_cache_invalidate_and_agent_reload(
        self, e2e_cache, e2e_registry, e2e_loader, e2e_prompt_name
    ):
        """Invalidate cache, loader falls to MLflow tier 2, re-caches."""
        name = e2e_prompt_name("reload")
        template = "Reload test for {{context.brand_name}}."

        # Register prompt as PRODUCTION in MLflow
        info = e2e_registry.register_prompt(
            name=name, template=template, tags={"state": "PRODUCTION"}
        )

        # Pre-populate cache
        await e2e_cache.set_prompt(name, "Old cached version", ttl=300)
        cached = await e2e_cache.get_prompt(name)
        assert cached == "Old cached version"

        # Invalidate cache
        deleted = await e2e_cache.invalidate_prompt(name)
        assert deleted >= 1

        # Loader should now fall through to MLflow tier 2
        loaded = await e2e_loader.load(
            name=name,
            variables={"context.brand_name": "TestBrand"},
            fallback_template="Fallback",
        )
        assert "Reload test" in loaded or "TestBrand" in loaded

        # Verify it was re-cached in Redis
        re_cached = await e2e_cache.get_prompt(name)
        assert re_cached is not None
