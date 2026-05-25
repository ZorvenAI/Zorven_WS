"""Integration tests for domain scorers (WF1 + WF2 + ILA).

Verifies all 12 domain scorers are valid MLflow Scorer instances
and that the grouped lists have the correct counts and names.
"""

from tests.conftest import requires_mlflow


@requires_mlflow
class TestWf1ScorerMlflowCompatibility:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        from app.scorers.wf1 import WF1_SCORERS

        for s in WF1_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_wf1_scorers_list_has_five(self):
        from app.scorers.wf1 import WF1_SCORERS

        assert len(WF1_SCORERS) == 5
        names = {s.name for s in WF1_SCORERS}
        assert names == {
            "market_completeness",
            "competitor_accuracy",
            "persona_quality",
            "trend_relevance",
            "voca_sentiment",
        }


@requires_mlflow
class TestWf2ScorerMlflowCompatibility:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        from app.scorers.wf2 import WF2_SCORERS

        for s in WF2_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_wf2_scorers_list_has_five(self):
        from app.scorers.wf2 import WF2_SCORERS

        assert len(WF2_SCORERS) == 5
        names = {s.name for s in WF2_SCORERS}
        assert names == {
            "positioning_clarity",
            "architecture_coherence",
            "voice_consistency",
            "name_quality",
            "narrative_engagement",
        }


@requires_mlflow
class TestIlaScorerMlflowCompatibility:
    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        from app.scorers.ila import ILA_SCORERS

        for s in ILA_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_ila_scorers_list_has_two(self):
        from app.scorers.ila import ILA_SCORERS

        assert len(ILA_SCORERS) == 2
        names = {s.name for s in ILA_SCORERS}
        assert names == {
            "learning_depth",
            "meta_policy",
        }
