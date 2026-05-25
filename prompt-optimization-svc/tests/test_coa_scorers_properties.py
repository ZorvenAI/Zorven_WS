"""Hypothesis property tests for COA scorers (US-024)."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.scorers.coa.data_grounding import data_grounding
from app.scorers.coa.guardrail_compliance import guardrail_compliance
from app.scorers.coa.prioritization_quality import prioritization_quality
from app.scorers.coa.recommendation_actionability import recommendation_actionability


class TestRecommendationActionabilityProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = recommendation_actionability(
            inputs="test", outputs=text, expectations=None
        )
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, text):
        result = recommendation_actionability(
            inputs=text, outputs=text, expectations=None
        )
        assert result is not None


class TestGuardrailComplianceProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = guardrail_compliance(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "passed": st.just(True),
                    "rule_id": st.text(min_size=1, max_size=5),
                    "message": st.text(max_size=20),
                    "action": st.just("allow"),
                }
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_all_passed_scores_1(self, results):
        out = json.dumps({"guardrail_report": {"results": results}})
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "passed": st.just(False),
                    "rule_id": st.text(min_size=1, max_size=5),
                    "message": st.text(max_size=20),
                    "action": st.just("block"),
                }
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_any_failed_scores_0(self, results):
        out = json.dumps({"guardrail_report": {"results": results}})
        result = guardrail_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0


class TestDataGroundingProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = data_grounding(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0


class TestPrioritizationQualityProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = prioritization_quality(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    def test_deterministic(self):
        out = json.dumps(
            {
                "recommendations": [
                    {
                        "action_type": "pause",
                        "priority": "high",
                    },
                    {
                        "action_type": "scale",
                        "priority": "medium",
                    },
                ]
            }
        )
        r1 = prioritization_quality(inputs="test", outputs=out, expectations=None)
        r2 = prioritization_quality(inputs="test", outputs=out, expectations=None)
        assert r1.value == r2.value
