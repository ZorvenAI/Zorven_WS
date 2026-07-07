"""Documentation validation tests for US-061 operational runbook.

Verifies runbook completeness, required sections, diagrams,
README link, and that referenced functions exist in the codebase.
"""

from pathlib import Path

import pytest

# Project root relative to this test file
PROJECT_ROOT = Path(__file__).parent.parent


class TestRunbookValidation:
    """Verify operational runbook completeness and accuracy."""

    @pytest.fixture(autouse=True)
    def _load_runbook(self):
        """Load runbook content once per test."""
        runbook_path = PROJECT_ROOT / "docs" / "operational_runbook.md"
        self.runbook_path = runbook_path
        if runbook_path.exists():
            self.runbook_content = runbook_path.read_text(encoding="utf-8")
        else:
            self.runbook_content = ""

    def test_runbook_file_exists(self):
        """docs/operational_runbook.md exists."""
        assert self.runbook_path.exists(), f"Runbook not found at {self.runbook_path}"

    def test_runbook_has_mlflow_recovery_section(self):
        """Runbook has MLflow Recovery section."""
        assert "MLflow Recovery" in self.runbook_content

    def test_runbook_has_redis_cache_section(self):
        """Runbook has Redis Cache Flush section."""
        assert "Redis Cache Flush" in self.runbook_content

    def test_runbook_has_kafka_lag_section(self):
        """Runbook has Kafka Consumer Lag section."""
        assert "Kafka Consumer Lag" in self.runbook_content

    def test_runbook_has_rollback_section(self):
        """Runbook has Rollback Procedure section."""
        assert "Rollback Procedure" in self.runbook_content

    def test_runbook_has_approval_section(self):
        """Runbook has Approval Workflow section."""
        assert "Approval Workflow" in self.runbook_content

    def test_runbook_has_lifecycle_diagram(self):
        """Runbook has Mermaid lifecycle state diagram."""
        assert "stateDiagram" in self.runbook_content
        # Verify key states appear in the diagram
        assert "DRAFT" in self.runbook_content
        assert "STAGING" in self.runbook_content
        assert "CANARY" in self.runbook_content
        assert "PRODUCTION" in self.runbook_content
        assert "ARCHIVED" in self.runbook_content
        assert "REJECTED" in self.runbook_content
        assert "ROLLED_BACK" in self.runbook_content
        assert "TENANT_OVERRIDE" in self.runbook_content

    def test_runbook_has_canary_diagram(self):
        """Runbook has Mermaid canary flow diagram."""
        # Look for the canary flow section with a flowchart
        assert "Canary" in self.runbook_content
        # Should have canary-specific diagram elements
        assert "SHA-256" in self.runbook_content
        assert "10%" in self.runbook_content

    def test_readme_links_to_runbook(self):
        """README.md contains link to operational runbook."""
        readme_path = PROJECT_ROOT / "README.md"
        assert readme_path.exists(), f"README.md not found at {readme_path}"
        readme_content = readme_path.read_text(encoding="utf-8")
        assert "operational_runbook.md" in readme_content

    def test_runbook_references_valid_functions(self):
        """Functions mentioned in runbook are importable."""
        # Key functions that must exist in the codebase
        from app.logic.rollback_manager import rollback_to_version

        assert callable(rollback_to_version)

        from app.cache.prompt_cache import PromptCacheManager

        assert hasattr(PromptCacheManager, "invalidate_prompt")

        from app.logic.approval_gate import approve_run, reject_run, requires_approval

        assert callable(approve_run)
        assert callable(reject_run)
        assert callable(requires_approval)

        from app.logic.canary_manager import CanaryManager, is_canary_request

        assert callable(is_canary_request)
        assert hasattr(CanaryManager, "start_canary")
        assert hasattr(CanaryManager, "check_canary_regression")
        assert hasattr(CanaryManager, "rollback_canary")

        from app.logic.circuit_breaker import MLflowCircuitBreaker

        assert hasattr(MLflowCircuitBreaker, "should_allow_request")
        assert hasattr(MLflowCircuitBreaker, "record_success")
        assert hasattr(MLflowCircuitBreaker, "record_failure")

        from app.tasks.prompt_health_check import prompt_health_check

        assert callable(prompt_health_check)
