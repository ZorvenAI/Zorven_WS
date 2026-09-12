"""L-04: Tenant prompt customization tests.

Tests lifecycle extensions, scaffold endpoint, dataset floor checks,
and canary tenant-aware promotion.
"""

import pytest

from app.logic.lifecycle import (
    InvalidTransitionError,
    PromptLifecycleManager,
    PromptState,
    VALID_TRANSITIONS,
)
from app.services.mlflow_registry import MLflowPromptRegistry
from .conftest import MLFLOW_URI, requires_mlflow


# ── Lifecycle transitions ──


class TestCanaryToTenantOverrideTransition:
    """The CANARY → TENANT_OVERRIDE path exists and works."""

    def test_canary_allows_tenant_override(self):
        allowed = VALID_TRANSITIONS[PromptState.CANARY]
        assert PromptState.TENANT_OVERRIDE in allowed

    def test_draft_to_tenant_override_shortcut_still_valid(self):
        allowed = VALID_TRANSITIONS[PromptState.DRAFT]
        assert PromptState.TENANT_OVERRIDE in allowed

    def test_canary_still_allows_production(self):
        allowed = VALID_TRANSITIONS[PromptState.CANARY]
        assert PromptState.PRODUCTION in allowed

    def test_canary_still_allows_rolled_back(self):
        allowed = VALID_TRANSITIONS[PromptState.CANARY]
        assert PromptState.ROLLED_BACK in allowed

    def test_validate_transition_accepts_canary_to_tenant_override(self):
        mgr = PromptLifecycleManager(
            MLflowPromptRegistry(MLFLOW_URI), lifecycle_producer=None
        )
        assert mgr.validate_transition(PromptState.CANARY, PromptState.TENANT_OVERRIDE)

    def test_staging_to_tenant_override_still_invalid(self):
        mgr = PromptLifecycleManager(
            MLflowPromptRegistry(MLFLOW_URI), lifecycle_producer=None
        )
        with pytest.raises(InvalidTransitionError):
            mgr.validate_transition(PromptState.STAGING, PromptState.TENANT_OVERRIDE)


@requires_mlflow
class TestPromoteToTenantOverride:
    """promote_to_tenant_override archives the previous override."""

    @pytest.fixture
    def manager(self):
        registry = MLflowPromptRegistry(MLFLOW_URI)
        return PromptLifecycleManager(registry, lifecycle_producer=None)

    def test_promote_canary_to_tenant_override(self, manager):
        name = "__test_l04_promote"
        reg_info = manager.registry.register_prompt(
            name=name,
            template="v1 canary",
            tags={"state": "CANARY", "tenant_id": "t-1"},
        )
        result = manager.promote_to_tenant_override(
            name, reg_info.version, tenant_id="t-1"
        )
        assert result is True
        updated = manager.registry.get_prompt_by_state(
            name, "TENANT_OVERRIDE", tenant_id="t-1"
        )
        assert updated is not None
        assert updated.version == reg_info.version

    def test_promote_archives_previous_override(self, manager):
        name = "__test_l04_archive"
        old = manager.registry.register_prompt(
            name=name,
            template="old override",
            tags={"state": "TENANT_OVERRIDE", "tenant_id": "t-2"},
        )
        new = manager.registry.register_prompt(
            name=name,
            template="new canary",
            tags={"state": "CANARY", "tenant_id": "t-2"},
        )
        manager.promote_to_tenant_override(name, new.version, tenant_id="t-2")

        old_state = manager.registry.get_prompt_by_state(
            name, "ARCHIVED", tenant_id="t-2"
        )
        assert old_state is not None
        assert old_state.version == old.version


# ── Scaffold endpoint ──


@requires_mlflow
class TestScaffoldEndpoint:
    """POST /v1/prompts/scaffold-tenant creates TENANT_OVERRIDE clones."""

    @pytest.fixture
    async def client(self):
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    async def test_scaffold_creates_overrides(self, client):
        resp = await client.post(
            "/v1/prompts/scaffold-tenant",
            json={"tenant_id": "__test_scaffold_t1"},
            headers={"X-User-Role": "ADMIN"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["tenant_id"] == "__test_scaffold_t1"
        assert data["scaffolded"] >= 1
        assert len(data["prompt_names"]) == data["scaffolded"]

    async def test_scaffold_is_idempotent(self, client):
        tenant = "__test_scaffold_idem"
        await client.post(
            "/v1/prompts/scaffold-tenant",
            json={"tenant_id": tenant},
            headers={"X-User-Role": "ADMIN"},
        )
        resp = await client.post(
            "/v1/prompts/scaffold-tenant",
            json={"tenant_id": tenant},
            headers={"X-User-Role": "ADMIN"},
        )
        data = resp.json()
        assert data["scaffolded"] == 0
        assert data["skipped"] >= 1

    async def test_scaffold_rejects_empty_tenant(self, client):
        resp = await client.post(
            "/v1/prompts/scaffold-tenant",
            json={"tenant_id": ""},
            headers={"X-User-Role": "ADMIN"},
        )
        assert resp.status_code == 422


# ── Dataset floor ──


class TestDatasetFloor:
    """The tenant GEPA floor check refuses below threshold."""

    def test_default_floor_is_50(self):
        from app.tasks.optimize_tenant_oia import DEFAULT_DATASET_FLOOR

        assert DEFAULT_DATASET_FLOOR == 50


# ── Canary tenant-aware promotion ──


class TestCanaryTenantAware:
    """CanaryState carries tenant_id through start → promote."""

    def test_canary_state_has_tenant_id(self):
        from app.logic.canary_manager import CanaryState
        from datetime import datetime, timezone

        state = CanaryState(
            prompt_name="test",
            canary_version=2,
            production_version=1,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            agent_code="oia",
            tenant_id="t-1",
        )
        assert state.tenant_id == "t-1"

    def test_canary_state_default_tenant_is_empty(self):
        from app.logic.canary_manager import CanaryState
        from datetime import datetime, timezone

        state = CanaryState(
            prompt_name="test",
            canary_version=2,
            production_version=1,
            started_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc),
            agent_code="oia",
        )
        assert state.tenant_id == ""


# ── TenantConfig model ──


class TestTenantConfigModel:
    """min_gepa_dataset_size column exists with correct default."""

    def test_model_has_min_gepa_dataset_size(self):
        from app.models.tenant_config import TenantConfig

        assert hasattr(TenantConfig, "min_gepa_dataset_size")

    def test_server_default_is_50(self):
        from app.models.tenant_config import TenantConfig

        col = TenantConfig.__table__.columns["min_gepa_dataset_size"]
        assert str(col.server_default.arg) == "50"


# ── Optimization runner threading ──


class TestRunnerTenantId:
    """run_group_optimization accepts tenant_id kwarg."""

    def test_accepts_tenant_id_kwarg(self):
        import inspect
        from app.tasks.optimization_runner import run_group_optimization

        sig = inspect.signature(run_group_optimization)
        assert "tenant_id" in sig.parameters

    def test_load_golden_dataset_accepts_tenant_id(self):
        import inspect
        from app.tasks.optimization_runner import _load_golden_dataset

        sig = inspect.signature(_load_golden_dataset)
        assert "tenant_id" in sig.parameters
