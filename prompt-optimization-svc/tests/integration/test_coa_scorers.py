"""Integration tests for COA scorers (US-024)."""

from tests.conftest import requires_mlflow


@requires_mlflow
class TestCoaScorerMlflowCompatibility:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        from app.scorers.coa import COA_SCORERS

        for s in COA_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_coa_scorers_list_has_four(self):
        from app.scorers.coa import COA_SCORERS

        assert len(COA_SCORERS) == 4
        names = {s.name for s in COA_SCORERS}
        assert names == {
            "recommendation_actionability",
            "guardrail_compliance",
            "data_grounding",
            "prioritization_quality",
        }
