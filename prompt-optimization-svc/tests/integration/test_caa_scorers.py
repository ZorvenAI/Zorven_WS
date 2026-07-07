"""Integration tests for CAA scorers (US-023)."""

from tests.conftest import requires_mlflow


@requires_mlflow
class TestCaaScorerMlflowCompatibility:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        from app.scorers.caa import CAA_SCORERS

        for s in CAA_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_caa_scorers_list_has_four(self):
        from app.scorers.caa import CAA_SCORERS

        assert len(CAA_SCORERS) == 4
        names = {s.name for s in CAA_SCORERS}
        assert names == {
            "structure_validity",
            "budget_rationality",
            "funnel_coverage",
            "targeting_quality",
        }
