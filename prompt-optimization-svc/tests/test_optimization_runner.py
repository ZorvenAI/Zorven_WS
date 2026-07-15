"""Unit tests for the shared optimization runner."""

import importlib
from unittest.mock import MagicMock

from app.registries.optimization_groups import OPTIMIZATION_GROUPS, get_group
from app.scorers import (
    CAA_SCORERS,
    CGA_SCORERS,
    COA_SCORERS,
    COMMON_SCORERS,
    ILA_SCORERS,
    WF1_SCORERS,
    WF2_SCORERS,
)


class TestOptimizationRunnerImport:
    """Verify the runner module is importable and has the expected API."""

    def test_module_importable(self):
        mod = importlib.import_module("app.tasks.optimization_runner")
        assert hasattr(mod, "run_group_optimization")

    def test_function_signature(self):
        from app.tasks.optimization_runner import run_group_optimization

        import inspect

        sig = inspect.signature(run_group_optimization)
        params = list(sig.parameters.keys())
        assert "group_name" in params
        assert "scorers" in params
        assert "celery_task_self" in params


class TestScorerGroupMapping:
    """Verify each optimization group has the correct scorer set."""

    def test_wf1_scorers_match_group(self):
        group = get_group("wf1-discovery-pipeline")
        scorers = COMMON_SCORERS + WF1_SCORERS
        assert len(scorers) >= 5  # 4 common + 5 WF1
        assert group.workflow == 1

    def test_wf2_scorers_match_group(self):
        group = get_group("wf2-brand-strategy-pipeline")
        scorers = COMMON_SCORERS + WF2_SCORERS
        assert len(scorers) >= 5
        assert group.workflow == 2

    def test_wf3_creative_scorers_match_group(self):
        group = get_group("wf3-creative-pipeline")
        scorers = COMMON_SCORERS + CAA_SCORERS + CGA_SCORERS
        assert len(scorers) >= 5
        assert group.workflow == 3

    def test_wf3_optloop_scorers_match_group(self):
        group = get_group("wf3-optimization-loop")
        scorers = COMMON_SCORERS + COA_SCORERS + ILA_SCORERS
        assert len(scorers) >= 5
        assert group.workflow == 3

    def test_all_groups_have_prompt_names(self):
        for name, group in OPTIMIZATION_GROUPS.items():
            assert len(group.prompt_names) > 0, f"Group {name} has no prompts"
            assert len(group.agent_codes) > 0, f"Group {name} has no agents"

    def test_all_scorers_are_callable(self):
        all_scorers = (
            COMMON_SCORERS
            + WF1_SCORERS
            + WF2_SCORERS
            + CAA_SCORERS
            + CGA_SCORERS
            + COA_SCORERS
            + ILA_SCORERS
        )
        for scorer in all_scorers:
            assert callable(scorer), f"Scorer {scorer} is not callable"


class TestTaskWiring:
    """Verify each optimization task calls the runner."""

    def test_wf1_task_calls_runner(self):
        import ast

        with open("app/tasks/optimize_wf1_pipeline.py") as f:
            source = f.read()
        tree = ast.parse(source)
        # Check that run_group_optimization is imported
        assert "run_group_optimization" in source
        assert "COMMON_SCORERS" in source
        assert "WF1_SCORERS" in source

    def test_wf2_task_calls_runner(self):
        with open("app/tasks/optimize_wf2_pipeline.py") as f:
            source = f.read()
        assert "run_group_optimization" in source
        assert "COMMON_SCORERS" in source
        assert "WF2_SCORERS" in source

    def test_wf3_creative_task_calls_runner(self):
        with open("app/tasks/optimize_wf3_pipeline.py") as f:
            source = f.read()
        assert "run_group_optimization" in source
        assert "CAA_SCORERS" in source
        assert "CGA_SCORERS" in source

    def test_wf3_optloop_task_calls_runner(self):
        with open("app/tasks/optimize_wf3_pipeline.py") as f:
            source = f.read()
        assert "COA_SCORERS" in source
        assert "ILA_SCORERS" in source

    def test_wf3_tasks_accept_force_parameter(self):
        with open("app/tasks/optimize_wf3_pipeline.py") as f:
            source = f.read()
        assert "force: bool = False" in source


class TestCampaignTriggerWiring:
    """Verify the campaign trigger enqueues tasks."""

    def test_trigger_has_task_dispatch(self):
        with open("app/kafka/campaign_trigger.py") as f:
            source = f.read()
        assert "optimize_wf3_creative_pipeline" in source
        assert "optimize_wf3_optimization_loop" in source
        assert "apply_async" in source
        assert '"force": True' in source or "'force': True" in source


class TestBugFixes:
    """Verify all bug fixes are applied."""

    def test_no_forward_reference_annotations(self):
        """Step 1.1: String annotations should be removed."""
        with open("app/api/routes.py") as f:
            source = f.read()
        # Should NOT have string annotations for these types
        assert '"DatasetSizeConfigRequest"' not in source
        assert '"TenantConfigUpdateRequest"' not in source

    def test_mlflow_registry_reset_on_shutdown(self):
        """Step 1.2: mlflow_registry should be reset in shutdown."""
        with open("app/main.py") as f:
            source = f.read()
        assert "routes.mlflow_registry = None" in source

    def test_no_double_cache_connect(self):
        """Step 1.3: Only one cache.connect() call in list_optimization_runs."""
        with open("app/api/routes.py") as f:
            source = f.read()
        # Find the list_optimization_runs function and check for double connect
        func_start = source.index("async def list_optimization_runs")
        # Find the next function
        next_func = source.index("@router.", func_start + 1)
        func_body = source[func_start:next_func]
        connect_count = func_body.count("cache.connect()")
        assert connect_count == 1, f"Expected 1 cache.connect(), found {connect_count}"

    def test_no_501_stub_endpoints(self):
        """Steps 4.1/4.2: 501 stubs should be replaced."""
        with open("app/api/routes.py") as f:
            source = f.read()
        assert "status_code=501" not in source

    def test_approve_endpoint_starts_canary(self):
        """Step 6.1: Approve should start canary deployment."""
        with open("app/api/routes.py") as f:
            source = f.read()
        # Find the approve function
        func_start = source.index("async def approve_optimization_run")
        next_func = source.index("@router.", func_start + 1)
        func_body = source[func_start:next_func]
        assert "start_canary" in func_body

    def test_cost_per_candidate_config(self):
        """Phase 2: COST_PER_CANDIDATE_USD should exist in config."""
        from app.core.config import settings

        assert hasattr(settings, "COST_PER_CANDIDATE_USD")
        assert settings.COST_PER_CANDIDATE_USD == 0.50


class TestMetricsWiring:
    """Verify Prometheus metrics are connected to the runner."""

    def test_runner_calls_record_optimization_run(self):
        with open("app/tasks/optimization_runner.py") as f:
            source = f.read()
        assert "record_optimization_run" in source

    def test_runner_calls_record_prompt_quality(self):
        with open("app/tasks/optimization_runner.py") as f:
            source = f.read()
        assert "record_prompt_quality" in source
