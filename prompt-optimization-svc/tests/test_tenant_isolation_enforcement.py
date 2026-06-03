"""Unit tests for tenant isolation enforcement (US-040, OPT-10)."""

from dataclasses import dataclass
from typing import Optional

from app.logic.tenant_isolation import (
    DEFAULT_EXPERIMENT,
    filter_golden_examples_by_tenant,
    get_mlflow_experiment_name,
    validate_no_cross_tenant_data,
)


@dataclass
class _TenantExample:
    """Test helper — golden example with tenant_id."""

    prompt_name: str = "zorven-wf1-mra-system"
    agent_code: str = "mra"
    tenant_id: Optional[str] = None


def _example(tenant_id=None, idx=0):
    return _TenantExample(
        prompt_name=f"zorven-wf1-mra-system",
        agent_code="mra",
        tenant_id=tenant_id,
    )


class TestMlflowExperimentName:
    """AC-1: MLflow experiments namespaced by tenant_id."""

    def test_global_experiment(self):
        assert get_mlflow_experiment_name(None) == DEFAULT_EXPERIMENT

    def test_empty_string_is_global(self):
        assert get_mlflow_experiment_name("") == DEFAULT_EXPERIMENT

    def test_tenant_experiment(self):
        result = get_mlflow_experiment_name("tenant-abc")
        assert result == "prompt-optimization-tenant-tenant-abc"

    def test_tenant_experiment_format(self):
        result = get_mlflow_experiment_name("t1")
        assert result.startswith("prompt-optimization-tenant-")
        assert "t1" in result

    def test_default_constant(self):
        assert DEFAULT_EXPERIMENT == "prompt-optimization"


class TestFilterGoldenExamples:
    """AC-2: Golden dataset reads filter by tenant_id."""

    def test_global_examples_always_included(self):
        examples = [_example(tenant_id=None, idx=0)]
        result = filter_golden_examples_by_tenant(examples, "t1")
        assert len(result) == 1

    def test_matching_tenant_included(self):
        examples = [_example(tenant_id="t1", idx=0)]
        result = filter_golden_examples_by_tenant(examples, "t1")
        assert len(result) == 1

    def test_other_tenant_excluded(self):
        examples = [_example(tenant_id="t2", idx=0)]
        result = filter_golden_examples_by_tenant(examples, "t1")
        assert len(result) == 0

    def test_mixed_tenants(self):
        examples = [
            _example(tenant_id=None, idx=0),  # global
            _example(tenant_id="t1", idx=1),  # matching
            _example(tenant_id="t2", idx=2),  # other
        ]
        result = filter_golden_examples_by_tenant(examples, "t1")
        assert len(result) == 2  # global + t1

    def test_global_only_no_tenant(self):
        examples = [
            _example(tenant_id=None, idx=0),
            _example(tenant_id="t1", idx=1),
        ]
        result = filter_golden_examples_by_tenant(examples, None)
        assert len(result) == 1  # only global

    def test_empty_list(self):
        result = filter_golden_examples_by_tenant([], "t1")
        assert result == []


class TestValidateNoCrossTenantData:
    """AC-3: GEPA reflection context never includes cross-tenant data."""

    def test_clean_context_passes(self):
        context = "Analyze brand performance for current tenant."
        assert validate_no_cross_tenant_data(context, "t1") is True

    def test_cross_tenant_detected(self):
        context = 'Using data from tenant_id="t2" for analysis.'
        assert validate_no_cross_tenant_data(context, "t1") is False

    def test_same_tenant_passes(self):
        context = 'Using data from tenant_id="t1" for analysis.'
        assert validate_no_cross_tenant_data(context, "t1") is True

    def test_empty_context_passes(self):
        assert validate_no_cross_tenant_data("", "t1") is True

    def test_null_values_pass(self):
        context = "tenant_id: null"
        assert validate_no_cross_tenant_data(context, "t1") is True

    def test_known_tenant_ids_check(self):
        context = "Using campaign data from tenant-abc for optimization."
        assert (
            validate_no_cross_tenant_data(
                context, "t1", all_tenant_ids=["tenant-abc", "t1"]
            )
            is False
        )

    def test_known_tenant_ids_same_passes(self):
        context = "Using campaign data from t1 for optimization."
        assert (
            validate_no_cross_tenant_data(context, "t1", all_tenant_ids=["t1", "t2"])
            is True
        )

    def test_no_tenant_reference_passes(self):
        context = "General prompt optimization instructions."
        assert validate_no_cross_tenant_data(context, "t1") is True
