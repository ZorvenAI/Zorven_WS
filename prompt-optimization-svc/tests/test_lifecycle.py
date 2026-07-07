"""Tests for prompt version lifecycle state machine using real MLflow (US-008)."""

import pytest

from app.logic.lifecycle import (
    InvalidTransitionError,
    PromptLifecycleManager,
    PromptState,
    SERVABLE_STATES,
)
from app.services.mlflow_registry import MLflowPromptRegistry, PromptInfo
from .conftest import MLFLOW_URI, requires_mlflow

TEST_PREFIX = "__test_lc_"


@requires_mlflow
class TestValidTransitions:
    @pytest.fixture
    def manager(self):
        registry = MLflowPromptRegistry(MLFLOW_URI)
        return PromptLifecycleManager(registry, lifecycle_producer=None)

    @pytest.fixture
    def prompt_name(self, manager):
        name = f"{TEST_PREFIX}trans"
        manager.registry.register_prompt(
            name=name, template="test", tags={"state": "DRAFT"}
        )
        return name

    def test_draft_to_staging(self, manager, prompt_name):
        result = manager.transition(
            prompt_name, 1, PromptState.DRAFT, PromptState.STAGING
        )
        assert result is True

    def test_staging_to_canary(self, manager, prompt_name):
        result = manager.transition(
            prompt_name, 1, PromptState.STAGING, PromptState.CANARY
        )
        assert result is True

    def test_canary_to_production(self, manager, prompt_name):
        result = manager.transition(
            prompt_name, 1, PromptState.CANARY, PromptState.PRODUCTION
        )
        assert result is True

    def test_staging_to_rejected(self, manager, prompt_name):
        result = manager.transition(
            prompt_name, 1, PromptState.STAGING, PromptState.REJECTED
        )
        assert result is True

    def test_canary_to_rolled_back(self, manager, prompt_name):
        result = manager.transition(
            prompt_name, 1, PromptState.CANARY, PromptState.ROLLED_BACK
        )
        assert result is True

    def test_draft_to_tenant_override(self, manager, prompt_name):
        result = manager.transition(
            prompt_name, 1, PromptState.DRAFT, PromptState.TENANT_OVERRIDE,
            tenant_id="t-1",
        )
        assert result is True


class TestInvalidTransitions:
    @pytest.fixture
    def manager(self):
        registry = MLflowPromptRegistry(MLFLOW_URI)
        return PromptLifecycleManager(registry, lifecycle_producer=None)

    def test_draft_to_production_invalid(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.validate_transition(
                PromptState.DRAFT, PromptState.PRODUCTION
            )

    def test_archived_to_anything_invalid(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.validate_transition(
                PromptState.ARCHIVED, PromptState.DRAFT
            )

    def test_rejected_is_terminal(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.validate_transition(
                PromptState.REJECTED, PromptState.STAGING
            )

    def test_error_message_includes_allowed(self):
        try:
            PromptLifecycleManager(
                MLflowPromptRegistry(MLFLOW_URI)
            ).validate_transition(PromptState.DRAFT, PromptState.PRODUCTION)
        except InvalidTransitionError as e:
            assert "STAGING" in str(e)


@requires_mlflow
class TestPromoteToProduction:
    @pytest.fixture
    def manager(self):
        registry = MLflowPromptRegistry(MLFLOW_URI)
        return PromptLifecycleManager(registry, lifecycle_producer=None)

    def test_promote_no_previous_production(self, manager):
        name = f"{TEST_PREFIX}promo_new"
        reg_info = manager.registry.register_prompt(
            name=name, template="new", tags={"state": "CANARY"}
        )
        manager.promote_to_production(name, reg_info.version)
        updated = manager.registry.get_prompt(name)
        assert updated.tags.get("state") == "PRODUCTION"


@requires_mlflow
class TestReject:
    @pytest.fixture
    def manager(self):
        registry = MLflowPromptRegistry(MLFLOW_URI)
        return PromptLifecycleManager(registry, lifecycle_producer=None)

    def test_reject_sets_state(self, manager):
        name = f"{TEST_PREFIX}reject"
        reg_info = manager.registry.register_prompt(
            name=name, template="reject me", tags={"state": "STAGING"}
        )
        manager.reject(name, reg_info.version)
        updated = manager.registry.get_prompt(name)
        assert updated.tags.get("state") == "REJECTED"


class TestGetProductionVersion:
    def test_staging_not_served(self):
        assert not PromptLifecycleManager.is_servable(PromptState.STAGING)
        assert not PromptLifecycleManager.is_servable(PromptState.DRAFT)

    def test_production_is_servable(self):
        assert PromptLifecycleManager.is_servable(PromptState.PRODUCTION)
        assert PromptLifecycleManager.is_servable(PromptState.TENANT_OVERRIDE)
        assert PromptLifecycleManager.is_servable(PromptState.CANARY)
