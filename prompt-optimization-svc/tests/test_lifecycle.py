"""Tests for prompt version lifecycle state machine (§3.3)."""

from unittest.mock import MagicMock

import pytest

from app.logic.lifecycle import (
    InvalidTransitionError,
    PromptLifecycleManager,
    PromptState,
    SERVABLE_STATES,
    VALID_TRANSITIONS,
)
from app.services.mlflow_registry import PromptInfo


@pytest.fixture
def mock_registry():
    """Mock MLflowPromptRegistry."""
    reg = MagicMock()
    reg.set_prompt_state = MagicMock()
    reg.get_prompt_by_state = MagicMock(return_value=None)
    return reg


@pytest.fixture
def mock_producer():
    """Mock LifecycleProducer."""
    prod = MagicMock()
    prod.send_lifecycle_event_sync = MagicMock()
    return prod


@pytest.fixture
def manager(mock_registry, mock_producer):
    """PromptLifecycleManager with mocked dependencies."""
    return PromptLifecycleManager(mock_registry, mock_producer)


class TestValidTransitions:
    """Test all valid lifecycle transitions."""

    def test_draft_to_staging(self, manager, mock_registry):
        result = manager.transition("test", 1, PromptState.DRAFT, PromptState.STAGING)
        assert result is True
        mock_registry.set_prompt_state.assert_called_with("test", 1, "STAGING")

    def test_staging_to_canary(self, manager, mock_registry):
        result = manager.transition("test", 1, PromptState.STAGING, PromptState.CANARY)
        assert result is True
        mock_registry.set_prompt_state.assert_called_with("test", 1, "CANARY")

    def test_canary_to_production(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.CANARY, PromptState.PRODUCTION
        )
        assert result is True

    def test_production_to_archived(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.PRODUCTION, PromptState.ARCHIVED
        )
        assert result is True

    def test_staging_to_rejected(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.STAGING, PromptState.REJECTED
        )
        assert result is True

    def test_canary_to_rolled_back(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.CANARY, PromptState.ROLLED_BACK
        )
        assert result is True

    def test_production_to_rolled_back(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.PRODUCTION, PromptState.ROLLED_BACK
        )
        assert result is True

    def test_draft_to_tenant_override(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.DRAFT, PromptState.TENANT_OVERRIDE, tenant_id="t-1"
        )
        assert result is True

    def test_tenant_override_to_archived(self, manager, mock_registry):
        result = manager.transition(
            "test", 1, PromptState.TENANT_OVERRIDE, PromptState.ARCHIVED
        )
        assert result is True


class TestInvalidTransitions:
    """Test that invalid transitions are rejected."""

    def test_draft_to_production_invalid(self, manager):
        """Cannot skip stages."""
        with pytest.raises(InvalidTransitionError):
            manager.transition("test", 1, PromptState.DRAFT, PromptState.PRODUCTION)

    def test_draft_to_canary_invalid(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.transition("test", 1, PromptState.DRAFT, PromptState.CANARY)

    def test_archived_to_anything_invalid(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.transition("test", 1, PromptState.ARCHIVED, PromptState.DRAFT)

    def test_rejected_to_anything_invalid(self, manager):
        """AC-3: Rejected versions are terminal."""
        with pytest.raises(InvalidTransitionError):
            manager.transition("test", 1, PromptState.REJECTED, PromptState.STAGING)

    def test_rolled_back_to_anything_invalid(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.transition("test", 1, PromptState.ROLLED_BACK, PromptState.DRAFT)

    def test_error_message_includes_allowed_states(self):
        try:
            PromptLifecycleManager(MagicMock()).validate_transition(
                PromptState.DRAFT, PromptState.PRODUCTION
            )
        except InvalidTransitionError as e:
            assert "STAGING" in str(e)
            assert "TENANT_OVERRIDE" in str(e)


class TestPromoteToProduction:
    """Test promotion with auto-archiving (AC-1, AC-2)."""

    def test_promote_archives_previous_production(self, manager, mock_registry):
        """AC-2: Previous PRODUCTION version is auto-archived."""
        # Existing production version
        mock_registry.get_prompt_by_state.return_value = PromptInfo(
            name="test", version=1, template="old", tags={"state": "PRODUCTION"}
        )
        manager.promote_to_production("test", 2)

        # Should archive v1 then promote v2
        calls = mock_registry.set_prompt_state.call_args_list
        assert len(calls) == 2
        assert calls[0] == (("test", 1, "ARCHIVED"),)
        assert calls[1] == (("test", 2, "PRODUCTION"),)

    def test_promote_no_previous_production(self, manager, mock_registry):
        """AC-1: Works when no previous PRODUCTION exists."""
        mock_registry.get_prompt_by_state.return_value = None
        manager.promote_to_production("test", 1)
        mock_registry.set_prompt_state.assert_called_once_with("test", 1, "PRODUCTION")

    def test_only_one_production_per_prompt(self, manager, mock_registry):
        """AC-1: After promotion, only one PRODUCTION version exists."""
        mock_registry.get_prompt_by_state.return_value = PromptInfo(
            name="test", version=1, template="old", tags={"state": "PRODUCTION"}
        )
        manager.promote_to_production("test", 2)
        # v1 archived, v2 promoted — only v2 is PRODUCTION
        archive_call = mock_registry.set_prompt_state.call_args_list[0]
        assert archive_call == (("test", 1, "ARCHIVED"),)


class TestReject:
    """Test rejection (AC-3)."""

    def test_reject_moves_to_rejected(self, manager, mock_registry):
        manager.reject("test", 1)
        mock_registry.set_prompt_state.assert_called_once_with("test", 1, "REJECTED")

    def test_reject_never_deletes(self, manager, mock_registry):
        """AC-3: Rejected versions retain traces, never hard-deleted."""
        manager.reject("test", 1)
        # No delete calls on the registry
        assert (
            not hasattr(mock_registry, "delete_prompt")
            or not mock_registry.delete_prompt.called
        )


class TestGetProductionVersion:
    """Test production version resolution (AC-4, AC-5)."""

    def test_tenant_override_takes_precedence(self, manager, mock_registry):
        """AC-5: TENANT_OVERRIDE takes precedence over global PRODUCTION."""
        tenant_override = PromptInfo(
            name="test",
            version=3,
            template="tenant",
            tags={"state": "TENANT_OVERRIDE", "tenant_id": "t-1"},
        )
        global_prod = PromptInfo(
            name="test",
            version=2,
            template="global",
            tags={"state": "PRODUCTION"},
        )

        def side_effect(name, state, tenant_id=None):
            if state == "TENANT_OVERRIDE" and tenant_id == "t-1":
                return tenant_override
            if state == "PRODUCTION" and tenant_id is None:
                return global_prod
            return None

        mock_registry.get_prompt_by_state.side_effect = side_effect

        result = manager.get_production_version("test", tenant_id="t-1")
        assert result.version == 3
        assert result.template == "tenant"

    def test_falls_back_to_global_production(self, manager, mock_registry):
        """When no tenant override, returns global PRODUCTION."""
        global_prod = PromptInfo(
            name="test",
            version=2,
            template="global",
            tags={"state": "PRODUCTION"},
        )

        def side_effect(name, state, tenant_id=None):
            if state == "TENANT_OVERRIDE":
                return None
            if state == "PRODUCTION":
                return global_prod
            return None

        mock_registry.get_prompt_by_state.side_effect = side_effect

        result = manager.get_production_version("test", tenant_id="t-1")
        assert result.version == 2

    def test_no_production_returns_none(self, manager, mock_registry):
        mock_registry.get_prompt_by_state.return_value = None
        result = manager.get_production_version("test")
        assert result is None

    def test_staging_not_served(self):
        """AC-4: STAGING versions are not served to production agents."""
        assert not PromptLifecycleManager.is_servable(PromptState.STAGING)
        assert not PromptLifecycleManager.is_servable(PromptState.DRAFT)
        assert not PromptLifecycleManager.is_servable(PromptState.REJECTED)

    def test_production_is_servable(self):
        assert PromptLifecycleManager.is_servable(PromptState.PRODUCTION)
        assert PromptLifecycleManager.is_servable(PromptState.TENANT_OVERRIDE)
        assert PromptLifecycleManager.is_servable(PromptState.CANARY)


class TestKafkaEvents:
    """Test lifecycle transitions emit Kafka events (AC-6)."""

    def test_transition_emits_event(self, manager, mock_producer):
        manager.transition("test", 1, PromptState.DRAFT, PromptState.STAGING)
        mock_producer.send_lifecycle_event_sync.assert_called_once_with(
            event_type="prompt.staged",
            prompt_name="test",
            version=1,
            from_state="DRAFT",
            to_state="STAGING",
            tenant_id=None,
        )

    def test_promotion_emits_promoted_event(
        self, manager, mock_registry, mock_producer
    ):
        mock_registry.get_prompt_by_state.return_value = None
        manager.promote_to_production("test", 1)
        mock_producer.send_lifecycle_event_sync.assert_called_once_with(
            event_type="prompt.promoted",
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
            tenant_id=None,
        )

    def test_rejection_emits_rejected_event(self, manager, mock_producer):
        manager.reject("test", 1)
        mock_producer.send_lifecycle_event_sync.assert_called_once_with(
            event_type="prompt.rejected",
            prompt_name="test",
            version=1,
            from_state="STAGING",
            to_state="REJECTED",
            tenant_id=None,
        )

    def test_rollback_emits_event(self, manager, mock_producer):
        manager.rollback("test", 1, PromptState.CANARY)
        mock_producer.send_lifecycle_event_sync.assert_called_once_with(
            event_type="prompt.rolled_back",
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="ROLLED_BACK",
            tenant_id=None,
        )

    def test_no_event_without_producer(self, mock_registry):
        """Works without Kafka producer (graceful degradation)."""
        mgr = PromptLifecycleManager(mock_registry, lifecycle_producer=None)
        result = mgr.transition("test", 1, PromptState.DRAFT, PromptState.STAGING)
        assert result is True


class TestRollback:
    """Test rollback from various states."""

    def test_rollback_from_canary(self, manager, mock_registry):
        manager.rollback("test", 1, PromptState.CANARY)
        mock_registry.set_prompt_state.assert_called_with("test", 1, "ROLLED_BACK")

    def test_rollback_from_production(self, manager, mock_registry):
        manager.rollback("test", 1, PromptState.PRODUCTION)
        mock_registry.set_prompt_state.assert_called_with("test", 1, "ROLLED_BACK")

    def test_rollback_from_staging_invalid(self, manager):
        with pytest.raises(InvalidTransitionError):
            manager.rollback("test", 1, PromptState.STAGING)
