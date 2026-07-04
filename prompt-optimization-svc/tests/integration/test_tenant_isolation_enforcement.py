"""Integration tests for tenant isolation (US-040)."""

from app.datasets.golden_seed import GOLDEN_EXAMPLES
from app.logic.tenant_isolation import (
    filter_golden_examples_by_tenant,
    get_mlflow_experiment_name,
)


class TestGoldenExampleIsolation:
    def test_all_seed_examples_are_global(self):
        """Seed examples have no tenant_id — all treated as global."""
        result = filter_golden_examples_by_tenant(GOLDEN_EXAMPLES, "any-tenant")
        # All seed examples have no tenant_id attribute → all global
        assert len(result) == len(GOLDEN_EXAMPLES)

    def test_filter_with_none_tenant(self):
        result = filter_golden_examples_by_tenant(GOLDEN_EXAMPLES, None)
        assert len(result) == len(GOLDEN_EXAMPLES)


class TestExperimentNameFormat:
    def test_global_name_valid(self):
        name = get_mlflow_experiment_name(None)
        assert "/" not in name
        assert len(name) > 0

    def test_tenant_name_valid(self):
        name = get_mlflow_experiment_name("zorven-tenant-1")
        assert "/" not in name
        assert "zorven-tenant-1" in name
