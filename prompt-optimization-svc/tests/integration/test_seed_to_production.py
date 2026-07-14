"""Integration tests for seed_to_production (Phase 1 — auto-seed).

Requires real MLflow at POI_MLFLOW_TRACKING_URI (default http://localhost:5000).
No mocks — all tests hit the real MLflow prompt registry.
"""

import uuid

import pytest

from app.logic.lifecycle import PromptLifecycleManager, PromptState
from app.registries.prompt_catalog import PROMPT_CATALOG
from app.services.mlflow_registry import MLflowPromptRegistry
from app.services.prompt_seeder import SeedResult, seed_to_production

from .conftest import MLFLOW_URI, requires_mlflow

# Unique prefix per test run to avoid collisions with other tests
RUN_ID = uuid.uuid4().hex[:8]
TEST_PREFIX = f"__seedtest_{RUN_ID}_"


@pytest.mark.integration
@requires_mlflow
class TestSeedToProduction:
    """Seed-to-production lifecycle tests against real MLflow."""

    @pytest.fixture
    def registry(self):
        return MLflowPromptRegistry(MLFLOW_URI)

    @pytest.fixture
    def lcm(self, registry):
        return PromptLifecycleManager(registry)

    def test_seed_to_production_fresh(self, registry, lcm):
        """All catalog prompts reach PRODUCTION with promoted_at tag."""
        result = seed_to_production(registry, lcm)

        assert isinstance(result, SeedResult)
        assert result.errors == 0, f"Seed errors: {result.details}"
        # Every prompt should be either promoted (created) or already there (skipped)
        total = result.created + result.skipped
        assert total == len(PROMPT_CATALOG), (
            f"Expected {len(PROMPT_CATALOG)} total, got {total} "
            f"(created={result.created}, skipped={result.skipped})"
        )

        # Verify a sample prompt is at PRODUCTION with promoted_at
        sample = PROMPT_CATALOG[0]
        prod = registry.get_prompt_by_state(sample.name, "PRODUCTION")
        assert prod is not None, f"{sample.name} not at PRODUCTION"
        assert prod.tags.get(
            "promoted_at"
        ), f"{sample.name} missing promoted_at timestamp"

    def test_seed_to_production_idempotent(self, registry, lcm):
        """Second run returns skipped=N, created=0."""
        # First run
        first = seed_to_production(registry, lcm)
        assert first.errors == 0

        # Second run — everything should be skipped
        second = seed_to_production(registry, lcm)
        assert (
            second.created == 0
        ), f"Expected 0 created on re-run, got {second.created}"
        assert second.skipped == len(PROMPT_CATALOG)
        assert second.errors == 0

    def test_seed_to_production_resumes_from_staging(self, registry, lcm):
        """A prompt stuck in STAGING completes to PRODUCTION."""
        name = f"{TEST_PREFIX}resume-staging"

        # Register and move to STAGING manually
        info = registry.register_prompt(
            name=name, template="Resume test", tags={"state": "DRAFT"}
        )
        registry.set_prompt_state(name, info.version, "STAGING")

        # Patch catalog temporarily to test just this prompt
        from app.registries.prompt_catalog import CatalogEntry

        original_catalog = list(PROMPT_CATALOG)
        test_entry = CatalogEntry(
            name=name,
            template="Resume test",
            tags={"state": "DRAFT"},
        )

        # Monkey-patch for this test
        import app.services.prompt_seeder as seeder_mod

        old_catalog = seeder_mod.PROMPT_CATALOG
        try:
            seeder_mod.PROMPT_CATALOG = [test_entry]
            result = seed_to_production(registry, lcm)
        finally:
            seeder_mod.PROMPT_CATALOG = old_catalog

        assert result.created == 1
        assert result.errors == 0

        prod = registry.get_prompt_by_state(name, "PRODUCTION")
        assert prod is not None

    def test_seed_to_production_resumes_from_canary(self, registry, lcm):
        """A prompt stuck in CANARY completes to PRODUCTION."""
        name = f"{TEST_PREFIX}resume-canary"

        # Register and move to CANARY manually
        info = registry.register_prompt(
            name=name, template="Canary resume test", tags={"state": "DRAFT"}
        )
        registry.set_prompt_state(name, info.version, "STAGING")
        registry.set_prompt_state(name, info.version, "CANARY")

        from app.registries.prompt_catalog import CatalogEntry

        test_entry = CatalogEntry(
            name=name,
            template="Canary resume test",
            tags={"state": "DRAFT"},
        )

        import app.services.prompt_seeder as seeder_mod

        old_catalog = seeder_mod.PROMPT_CATALOG
        try:
            seeder_mod.PROMPT_CATALOG = [test_entry]
            result = seed_to_production(registry, lcm)
        finally:
            seeder_mod.PROMPT_CATALOG = old_catalog

        assert result.created == 1
        assert result.errors == 0

        prod = registry.get_prompt_by_state(name, "PRODUCTION")
        assert prod is not None
        assert prod.tags.get("promoted_at") is not None

    def test_seed_to_production_skips_already_promoted(self, registry, lcm):
        """A prompt already at PRODUCTION is not re-registered."""
        name = f"{TEST_PREFIX}already-prod"

        # Register and walk to PRODUCTION manually
        info = registry.register_prompt(
            name=name, template="Already prod", tags={"state": "DRAFT"}
        )
        registry.set_prompt_state(name, info.version, "STAGING")
        registry.set_prompt_state(name, info.version, "CANARY")
        registry.set_prompt_state(name, info.version, "PRODUCTION")

        from app.registries.prompt_catalog import CatalogEntry

        test_entry = CatalogEntry(
            name=name,
            template="Already prod",
            tags={"state": "DRAFT"},
        )

        import app.services.prompt_seeder as seeder_mod

        old_catalog = seeder_mod.PROMPT_CATALOG
        try:
            seeder_mod.PROMPT_CATALOG = [test_entry]
            result = seed_to_production(registry, lcm)
        finally:
            seeder_mod.PROMPT_CATALOG = old_catalog

        assert result.created == 0
        assert result.skipped == 1
        assert result.errors == 0

    def test_production_endpoint_returns_seeded_prompt(self, registry, lcm):
        """After seeding, the lifecycle manager returns PRODUCTION version."""
        # Seed all prompts
        seed_to_production(registry, lcm)

        sample = PROMPT_CATALOG[0]
        prod = lcm.get_production_version(sample.name)
        assert prod is not None, f"No PRODUCTION version for {sample.name}"
        assert prod.template == sample.template
