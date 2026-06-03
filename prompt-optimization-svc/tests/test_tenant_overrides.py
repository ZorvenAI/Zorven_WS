"""Unit tests for tenant-specific prompt overrides (US-039)."""

from app.logic.lifecycle import VALID_TRANSITIONS, PromptState
from app.logic.tenant_override import TENANT_CACHE_KEY


class TestTenantOverrideLifecycle:
    """Lifecycle transitions for TENANT_OVERRIDE state."""

    def test_draft_to_tenant_override_valid(self):
        assert PromptState.TENANT_OVERRIDE in VALID_TRANSITIONS[PromptState.DRAFT]

    def test_tenant_override_to_archived_valid(self):
        assert PromptState.ARCHIVED in VALID_TRANSITIONS[PromptState.TENANT_OVERRIDE]

    def test_tenant_override_has_outgoing(self):
        assert len(VALID_TRANSITIONS[PromptState.TENANT_OVERRIDE]) >= 1


class TestTenantCacheKey:
    def test_key_format(self):
        key = TENANT_CACHE_KEY.format(name="zorven-wf3-cga-system", tenant_id="t1")
        assert key == "prompt:zorven-wf3-cga-system:tenant:t1"

    def test_key_includes_both_ids(self):
        key = TENANT_CACHE_KEY.format(name="test-prompt", tenant_id="tenant-abc")
        assert "test-prompt" in key
        assert "tenant-abc" in key


class TestCreateTenantOverride:
    async def test_returns_override_info(self):
        from app.logic.tenant_override import create_tenant_override

        result = await create_tenant_override(
            prompt_name="zorven-wf3-cga-system",
            tenant_id="t1",
            template="Override template for tenant t1",
        )
        assert result["prompt_name"] == "zorven-wf3-cga-system"
        assert result["tenant_id"] == "t1"
        assert result["template"] == "Override template for tenant t1"
        assert result["state"] == "TENANT_OVERRIDE"

    async def test_returns_version_zero_without_mlflow(self):
        from app.logic.tenant_override import create_tenant_override

        result = await create_tenant_override(
            prompt_name="test",
            tenant_id="t1",
            template="template",
        )
        assert result["version"] == 0

    async def test_state_is_tenant_override(self):
        from app.logic.tenant_override import create_tenant_override

        result = await create_tenant_override(
            prompt_name="test",
            tenant_id="t2",
            template="template",
        )
        assert result["state"] == "TENANT_OVERRIDE"


class TestDeleteTenantOverride:
    async def test_returns_false_without_registry(self):
        from app.logic.tenant_override import delete_tenant_override

        result = await delete_tenant_override(
            prompt_name="test",
            tenant_id="t1",
        )
        assert result is False

    async def test_returns_false_no_override_found(self):
        from app.logic.tenant_override import delete_tenant_override

        result = await delete_tenant_override(
            prompt_name="nonexistent",
            tenant_id="t1",
            mlflow_registry=None,
            prompt_cache=None,
        )
        assert result is False


class TestGetTenantOverride:
    async def test_returns_none_without_registry(self):
        from app.logic.tenant_override import get_tenant_override

        result = await get_tenant_override(
            prompt_name="test",
            tenant_id="t1",
            mlflow_registry=None,
        )
        assert result is None


class TestSchemas:
    def test_override_request_requires_template(self):
        from pydantic import ValidationError

        from app.api.schemas import TenantOverrideRequest

        try:
            TenantOverrideRequest(template="", tenant_id="t1")
            assert False, "Should reject empty template"
        except ValidationError:
            pass

    def test_override_request_requires_tenant_id(self):
        from pydantic import ValidationError

        from app.api.schemas import TenantOverrideRequest

        try:
            TenantOverrideRequest(template="text", tenant_id="")
            assert False, "Should reject empty tenant_id"
        except ValidationError:
            pass

    def test_override_request_valid(self):
        from app.api.schemas import TenantOverrideRequest

        req = TenantOverrideRequest(template="Override text", tenant_id="t1")
        assert req.template == "Override text"
        assert req.tenant_id == "t1"

    def test_override_response_fields(self):
        from app.api.schemas import TenantOverrideResponse

        resp = TenantOverrideResponse(
            prompt_name="test",
            tenant_id="t1",
            version=3,
            template="text",
        )
        assert resp.state == "TENANT_OVERRIDE"
        assert resp.version == 3
