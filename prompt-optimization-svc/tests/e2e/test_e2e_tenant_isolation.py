"""E2E tests for tenant isolation in optimization artifacts (US-060).

Exercises: experiment namespacing, golden example filtering, cache isolation,
OPT-10 cross-tenant block, loader tenant override priority,
two-tenant pipeline no-leakage.
"""

import uuid

import pytest

from app.logic.guardrails import run_candidate_guardrails
from app.logic.tenant_isolation import (
    filter_golden_examples_by_tenant,
    get_mlflow_experiment_name,
    validate_no_cross_tenant_data,
)


class _FakeExample:
    """Minimal object with tenant_id attribute for filtering tests."""

    def __init__(self, name: str, tenant_id=None):
        self.name = name
        self.tenant_id = tenant_id


@pytest.mark.e2e
class TestTenantIsolation:
    """Tenant scoping and data isolation verification."""

    def test_tenant_scoped_experiment_name(self):
        """Verify experiment names are tenant-scoped and sanitized."""
        # Global namespace
        assert get_mlflow_experiment_name(None) == "prompt-optimization"
        assert get_mlflow_experiment_name("") == "prompt-optimization"

        # Tenant-scoped
        assert (
            get_mlflow_experiment_name("acme-corp")
            == "prompt-optimization-tenant-acme-corp"
        )
        assert (
            get_mlflow_experiment_name("tenant_123")
            == "prompt-optimization-tenant-tenant_123"
        )

        # Special characters sanitized
        result = get_mlflow_experiment_name("tenant@evil/../hack")
        assert "@" not in result
        assert ".." not in result
        assert "/" not in result

        # All-special -> falls back to global
        assert get_mlflow_experiment_name("@!#$") == "prompt-optimization"

    def test_filter_golden_examples_by_tenant(self):
        """Tenant A excludes tenant B, includes global."""
        global_ex = _FakeExample("global-1", tenant_id=None)
        tenant_a_ex = _FakeExample("a-1", tenant_id="tenant-a")
        tenant_b_ex = _FakeExample("b-1", tenant_id="tenant-b")
        all_examples = [global_ex, tenant_a_ex, tenant_b_ex]

        # Filter for tenant A
        filtered_a = filter_golden_examples_by_tenant(all_examples, "tenant-a")
        assert global_ex in filtered_a
        assert tenant_a_ex in filtered_a
        assert tenant_b_ex not in filtered_a

        # Filter for tenant B
        filtered_b = filter_golden_examples_by_tenant(all_examples, "tenant-b")
        assert global_ex in filtered_b
        assert tenant_b_ex in filtered_b
        assert tenant_a_ex not in filtered_b

        # Global-only (no tenant)
        filtered_none = filter_golden_examples_by_tenant(all_examples, None)
        assert global_ex in filtered_none
        assert tenant_a_ex not in filtered_none
        assert tenant_b_ex not in filtered_none

    async def test_cache_tenant_isolation_no_cross_read(
        self, e2e_cache, e2e_prompt_name
    ):
        """Tenant A data invisible to tenant B."""
        name = e2e_prompt_name("tenant-iso")

        # Set tenant A override
        await e2e_cache.set_prompt(name, "Tenant A template", tenant_id="t-a", ttl=300)

        # Set tenant B override
        await e2e_cache.set_prompt(name, "Tenant B template", tenant_id="t-b", ttl=300)

        # Read tenant A — should get A's template, not B's
        cached_a = await e2e_cache.get_prompt(name, tenant_id="t-a")
        assert cached_a == "Tenant A template"

        # Read tenant B — should get B's template, not A's
        cached_b = await e2e_cache.get_prompt(name, tenant_id="t-b")
        assert cached_b == "Tenant B template"

        # Read global — should be None (no global production set)
        cached_global = await e2e_cache.get_prompt(name)
        assert cached_global is None

    def test_opt10_blocks_cross_tenant_data(self):
        """Cross-tenant data in reflection context detected by OPT-10."""
        # Reflection mentioning another tenant
        reflection_with_leak = (
            "Optimization context for ACME Corp. "
            'Previous run used tenant_id: "other-tenant-xyz" data.'
        )

        result = validate_no_cross_tenant_data(
            reflection_context=reflection_with_leak,
            tenant_id="acme-corp",
        )
        assert result is False  # Cross-tenant data detected

        # Clean reflection
        clean_reflection = (
            "Optimization context for ACME Corp. "
            'Previous run used tenant_id: "acme-corp" data.'
        )
        result_clean = validate_no_cross_tenant_data(
            reflection_context=clean_reflection,
            tenant_id="acme-corp",
        )
        assert result_clean is True

    async def test_loader_tenant_override_priority(
        self, e2e_cache, e2e_loader, e2e_prompt_name
    ):
        """Tenant override served before global production prompt."""
        name = e2e_prompt_name("override")

        # Set global production template
        await e2e_cache.set_prompt(name, "Global production template", ttl=300)

        # Set tenant-specific override
        await e2e_cache.set_prompt(
            name, "Tenant override template", tenant_id="override-tenant", ttl=300
        )

        # Load with tenant — should get override
        loaded_tenant = await e2e_loader.load(
            name=name,
            tenant_id="override-tenant",
            fallback_template="Fallback",
        )
        assert loaded_tenant == "Tenant override template"

        # Load without tenant — should get global
        loaded_global = await e2e_loader.load(
            name=name,
            fallback_template="Fallback",
        )
        assert loaded_global == "Global production template"

    async def test_full_pipeline_two_tenants_no_leakage(
        self, e2e_cache, e2e_loader, e2e_prompt_name
    ):
        """Two mini-pipelines for different tenants, no cache cross-reads."""
        name = e2e_prompt_name("two-tenant")
        tid_a = f"__e2e_tenant_a_{uuid.uuid4().hex[:6]}"
        tid_b = f"__e2e_tenant_b_{uuid.uuid4().hex[:6]}"

        # Simulate tenant A optimization result
        await e2e_cache.set_prompt(
            name, "Optimized for tenant A brand voice", tenant_id=tid_a, ttl=300
        )

        # Simulate tenant B optimization result
        await e2e_cache.set_prompt(
            name, "Optimized for tenant B brand voice", tenant_id=tid_b, ttl=300
        )

        # Verify tenant A loads its own prompt
        loaded_a = await e2e_loader.load(
            name=name, tenant_id=tid_a, fallback_template="Fallback"
        )
        assert "tenant A" in loaded_a

        # Verify tenant B loads its own prompt
        loaded_b = await e2e_loader.load(
            name=name, tenant_id=tid_b, fallback_template="Fallback"
        )
        assert "tenant B" in loaded_b

        # Verify no cross-contamination
        assert loaded_a != loaded_b

        # Validate no cross-tenant data in reflection context
        assert validate_no_cross_tenant_data(
            reflection_context=f"Optimizing for {tid_a}",
            tenant_id=tid_a,
            all_tenant_ids=[tid_a, tid_b],
        )
