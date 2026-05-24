"""Integration tests for joint optimizer (US-019).

Requires real MLflow.
"""

import pytest

from app.registries.optimization_groups import get_group
from app.services.gepa_optimizer import ZorvenGepaOptimizer
from app.services.joint_optimizer import JointOptimizer, JointOptimizationResult
from app.services.mlflow_registry import MLflowPromptRegistry

from .conftest import MLFLOW_URI, requires_mlflow



@pytest.mark.integration
@requires_mlflow
class TestJointOptimizerWithMLflow:
    """Test joint optimizer with real MLflow."""

    @pytest.fixture
    def optimizer(self):
        gepa = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)
        registry = MLflowPromptRegistry(MLFLOW_URI)
        return JointOptimizer(gepa, registry=registry)

    def test_optimize_group_returns_result(self, optimizer):
        """optimize_group returns JointOptimizationResult."""
        result = optimizer.optimize_group(
            "wf3-creative-pipeline",
            predict_fn=lambda **kw: "test output",
            train_data=[],
            scorers=[],
        )
        assert isinstance(result, JointOptimizationResult)
        assert result.group_name == "wf3-creative-pipeline"

    def test_optimize_group_error_for_unknown(self, optimizer):
        result = optimizer.optimize_group(
            "__nonexistent_xyz",
            predict_fn=lambda **kw: "",
            train_data=[],
            scorers=[],
        )
        assert result.error is not None
