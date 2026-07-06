"""Property-based invariant tests for US-061 runbook completeness.

Exhaustive checks that every config variable, lifecycle transition,
and Prometheus metric is documented in the runbook.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent


class TestRunbookProperties:
    """Invariant checks: code artifacts match runbook documentation."""

    @pytest.fixture(autouse=True)
    def _load_runbook(self):
        """Load runbook content once per test."""
        runbook_path = PROJECT_ROOT / "docs" / "operational_runbook.md"
        assert runbook_path.exists(), "Runbook must exist for property tests"
        self.runbook_content = runbook_path.read_text(encoding="utf-8")

    def test_all_config_vars_documented(self):
        """Every Settings field has a matching POI_* entry in runbook."""
        from app.core.config import Settings

        missing = []
        for field_name in Settings.model_fields:
            env_var = f"POI_{field_name.upper()}"
            if env_var not in self.runbook_content:
                missing.append(env_var)

        assert (
            not missing
        ), f"Config vars not documented in runbook: {', '.join(missing)}"

    def test_all_lifecycle_transitions_documented(self):
        """Every VALID_TRANSITIONS entry appears in the runbook."""
        from app.logic.lifecycle import VALID_TRANSITIONS

        missing = []
        for from_state, to_states in VALID_TRANSITIONS.items():
            for to_state in to_states:
                # Check the transition appears in the runbook
                # Mermaid format: FROM --> TO or FROM → TO
                from_name = from_state.value
                to_name = to_state.value
                # Check Mermaid diagram edge or transition table row
                has_mermaid_edge = f"{from_name} --> {to_name}" in self.runbook_content
                has_table_row = (
                    f"| {from_name} |" in self.runbook_content
                    and f"{to_name}"
                    in self.runbook_content.split(f"| {from_name} |")[-1].split("\n")[0]
                )
                if not has_mermaid_edge and not has_table_row:
                    missing.append(f"{from_name} -> {to_name}")

        assert (
            not missing
        ), f"Lifecycle transitions not documented: {', '.join(missing)}"

    def test_all_prometheus_metrics_documented(self):
        """Every Prometheus metric name from app/metrics appears in runbook."""
        from app import metrics as m

        # Collect all metric name strings from the metrics module
        metric_names = []
        for attr_name in dir(m):
            obj = getattr(m, attr_name)
            # Prometheus metrics have a _name attribute
            if hasattr(obj, "_name"):
                metric_names.append(obj._name)

        assert (
            len(metric_names) >= 8
        ), f"Expected at least 8 metrics, found {len(metric_names)}"

        missing = []
        for metric_name in metric_names:
            if metric_name not in self.runbook_content:
                missing.append(metric_name)

        assert not missing, f"Prometheus metrics not documented: {', '.join(missing)}"
