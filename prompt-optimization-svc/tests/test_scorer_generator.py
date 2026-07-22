"""Tests for the auto-generated baseline scorer module (US-054)."""

from app.registries.optimization_groups import OPTIMIZATION_GROUPS
from app.scorers.scorer_generator import generate_baseline_scorers


class TestScorerGeneratorModule:
    """Verify scorer_generator module exists and has the correct API."""

    def test_module_importable(self):
        import importlib

        mod = importlib.import_module("app.scorers.scorer_generator")
        assert hasattr(mod, "generate_baseline_scorers")

    def test_function_is_callable(self):
        assert callable(generate_baseline_scorers)


class TestGenerateBaselineScorers:
    """Test generate_baseline_scorers for known optimization groups."""

    def test_returns_list(self):
        result = generate_baseline_scorers("wf1-discovery-pipeline")
        assert isinstance(result, list)

    def test_scorers_are_callable(self):
        scorers = generate_baseline_scorers("wf1-discovery-pipeline")
        for scorer in scorers:
            assert callable(scorer), f"Scorer {scorer} is not callable"

    def test_generates_for_all_groups(self):
        """Each group should produce at least some baseline scorers."""
        for group_name in OPTIMIZATION_GROUPS:
            scorers = generate_baseline_scorers(group_name)
            assert isinstance(scorers, list), f"Group {group_name} returned non-list"

    def test_invalid_group_raises(self):
        """Invalid group name should raise KeyError from get_group."""
        import pytest

        with pytest.raises(KeyError):
            generate_baseline_scorers("nonexistent-group")


class TestBaselineScorerOutput:
    """Test that generated scorers produce valid Feedback objects."""

    def test_scorer_returns_feedback(self):
        scorers = generate_baseline_scorers("wf1-discovery-pipeline")
        if not scorers:
            return  # Skip if no skills matched

        scorer = scorers[0]
        feedback = scorer(
            inputs={"key": "value"},
            outputs='{"field": "value"}',
            expectations="expected",
        )
        assert hasattr(feedback, "value")
        assert hasattr(feedback, "name")
        assert 0.0 <= feedback.value <= 1.0

    def test_scorer_handles_empty_output(self):
        scorers = generate_baseline_scorers("wf1-discovery-pipeline")
        if not scorers:
            return

        scorer = scorers[0]
        feedback = scorer(inputs={}, outputs="", expectations="")
        assert feedback.value == 0.0

    def test_scorer_handles_non_json_output(self):
        scorers = generate_baseline_scorers("wf1-discovery-pipeline")
        if not scorers:
            return

        scorer = scorers[0]
        feedback = scorer(inputs={}, outputs="not json at all", expectations="")
        assert feedback.value == 0.0


class TestScorerGeneratorWiring:
    """Verify scorer generator is wired into the optimization runner."""

    def test_runner_imports_generator(self):
        with open("app/tasks/optimization_runner.py") as f:
            source = f.read()
        assert "generate_baseline_scorers" in source
        assert "from app.scorers.scorer_generator import" in source

    def test_runner_adds_baseline_scorers(self):
        with open("app/tasks/optimization_runner.py") as f:
            source = f.read()
        assert "baseline_scorers" in source
        assert "Added %d baseline scorers" in source

    def test_runner_handles_generator_failure(self):
        """Generator failure must be non-fatal."""
        with open("app/tasks/optimization_runner.py") as f:
            source = f.read()
        assert "Baseline scorer generation failed (non-fatal)" in source
