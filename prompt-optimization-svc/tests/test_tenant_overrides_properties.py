"""Hypothesis property tests for tenant overrides (US-039)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.tenant_override import TENANT_CACHE_KEY


class TestTenantOverrideProperties:
    @given(st.text(min_size=1, max_size=30), st.text(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_cache_key_always_non_empty(self, name, tenant_id):
        key = TENANT_CACHE_KEY.format(name=name, tenant_id=tenant_id)
        assert len(key) > 0
        assert "prompt:" in key
        assert ":tenant:" in key

    @given(st.text(min_size=1, max_size=30), st.text(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    async def test_create_never_raises(self, name, tenant_id):
        from app.logic.tenant_override import create_tenant_override

        result = await create_tenant_override(
            prompt_name=name,
            tenant_id=tenant_id,
            template="test template",
        )
        assert result["state"] == "TENANT_OVERRIDE"

    @given(st.text(min_size=1, max_size=30), st.text(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    async def test_get_returns_none_without_registry(self, name, tenant_id):
        from app.logic.tenant_override import get_tenant_override

        result = await get_tenant_override(name, tenant_id, mlflow_registry=None)
        assert result is None
