"""Hypothesis property tests for tenant isolation (US-040)."""

from dataclasses import dataclass
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.tenant_isolation import (
    filter_golden_examples_by_tenant,
    get_mlflow_experiment_name,
    validate_no_cross_tenant_data,
)


@dataclass
class _TenantExample:
    tenant_id: Optional[str] = None


class TestExperimentNameProperties:
    @given(st.text(min_size=1, max_size=30))
    @settings(max_examples=50, deadline=None)
    def test_always_contains_prefix(self, tenant_id):
        name = get_mlflow_experiment_name(tenant_id)
        assert "prompt-optimization" in name

    @given(st.text(min_size=1, max_size=30))
    @settings(max_examples=50, deadline=None)
    def test_tenant_name_always_longer_than_default(self, tenant_id):
        name = get_mlflow_experiment_name(tenant_id)
        default = get_mlflow_experiment_name(None)
        assert len(name) > len(default)


class TestFilterProperties:
    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=30, deadline=None)
    def test_other_tenant_never_in_result(self, tenant_id):
        examples = [
            _TenantExample(tenant_id="other-tenant-xyz"),
        ]
        result = filter_golden_examples_by_tenant(examples, tenant_id)
        for ex in result:
            assert ex.tenant_id is None or ex.tenant_id == tenant_id

    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=30, deadline=None)
    def test_global_always_included(self, tenant_id):
        examples = [_TenantExample(tenant_id=None)]
        result = filter_golden_examples_by_tenant(examples, tenant_id)
        assert len(result) == 1


class TestValidationProperties:
    @given(st.text(max_size=100), st.text(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_deterministic(self, context, tenant_id):
        r1 = validate_no_cross_tenant_data(context, tenant_id)
        r2 = validate_no_cross_tenant_data(context, tenant_id)
        assert r1 == r2
