"""Unit tests for joint multi-prompt optimization (US-019)."""

import pytest

from app.logic.prompt_naming import validate_prompt_name
from app.registries.optimization_groups import (
    OPTIMIZATION_GROUPS,
    OptimizationGroup,
    get_group,
)
from app.services.joint_optimizer import JointOptimizationResult, JointOptimizer
from app.services.gepa_optimizer import ZorvenGepaOptimizer
from .conftest import MLFLOW_URI, requires_mlflow


class TestOptimizationGroupRegistry:
    """AC-1: Group definition matches §4.2."""

    def test_wf3_creative_pipeline_exists(self):
        group = get_group("wf3-creative-pipeline")
        assert group.name == "wf3-creative-pipeline"

    def test_wf3_creative_has_caa_cga_adpub(self):
        group = get_group("wf3-creative-pipeline")
        assert "caa" in group.agent_codes
        assert "cga" in group.agent_codes
        assert "adpub" in group.agent_codes

    def test_wf3_creative_prompt_names(self):
        group = get_group("wf3-creative-pipeline")
        assert any("caa" in n for n in group.prompt_names)
        assert any("cga" in n for n in group.prompt_names)
        assert any("adpub" in n for n in group.prompt_names)

    def test_all_3_workflows_have_groups(self):
        workflows = {g.workflow for g in OPTIMIZATION_GROUPS.values()}
        assert {1, 2, 3} == workflows

    def test_all_groups_have_prompts(self):
        for name, group in OPTIMIZATION_GROUPS.items():
            assert len(group.prompt_names) >= 2, f"{name} has too few prompts"

    def test_all_prompt_names_valid(self):
        """All group prompt names follow §3.1 convention."""
        for name, group in OPTIMIZATION_GROUPS.items():
            for pn in group.prompt_names:
                parts = validate_prompt_name(pn)
                assert parts is not None, f"{pn} in {name} is invalid"

    def test_unknown_group_raises(self):
        with pytest.raises(KeyError, match="Unknown optimization group"):
            get_group("nonexistent-xyz")

    def test_group_is_frozen(self):
        group = get_group("wf3-creative-pipeline")
        with pytest.raises(AttributeError):
            group.name = "changed"


class TestJointOptimizationResult:
    def test_defaults(self):
        r = JointOptimizationResult()
        assert r.group_name == ""
        assert r.mlflow_run_id == ""
        assert r.promoted_as_set is False
        assert r.error is None

    def test_populated(self):
        r = JointOptimizationResult(
            group_name="wf3-creative-pipeline",
            mlflow_run_id="run-123",
            overall_score=0.85,
            promoted_as_set=True,
        )
        assert r.group_name == "wf3-creative-pipeline"
        assert r.promoted_as_set is True


class TestJointOptimizerErrorHandling:
    def test_unknown_group_returns_error(self):
        gepa = ZorvenGepaOptimizer(mlflow_tracking_uri=MLFLOW_URI)
        optimizer = JointOptimizer(gepa)
        result = optimizer.optimize_group(
            "nonexistent-xyz",
            predict_fn=lambda **kw: "",
            train_data=[],
            scorers=[],
        )
        assert result.error is not None
        assert "Unknown" in result.error
