"""Hypothesis property tests for CAA scorers (US-023)."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.scorers.caa.budget_rationality import budget_rationality
from app.scorers.caa.funnel_coverage import funnel_coverage
from app.scorers.caa.structure_validity import structure_validity
from app.scorers.caa.targeting_quality import targeting_quality


class TestStructureValidityProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = structure_validity(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, text):
        result = structure_validity(inputs=text, outputs=text, expectations=None)
        assert result is not None

    def test_deterministic(self):
        out = json.dumps(
            {
                "blueprint": {
                    "campaign_name": "Test",
                    "campaign_objective": "AWARENESS",
                    "ad_sets": [{"name": "X", "funnel_stage": "tofu", "targeting": {}}],
                }
            }
        )
        r1 = structure_validity(inputs="test", outputs=out, expectations=None)
        r2 = structure_validity(inputs="test", outputs=out, expectations=None)
        assert r1.value == r2.value


class TestBudgetRationalityProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = budget_rationality(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(
        st.lists(
            st.floats(
                min_value=0, max_value=100, allow_nan=False, allow_infinity=False
            ),
            min_size=1,
            max_size=4,
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_exact_100_scores_1(self, pcts):
        # Normalize to sum to exactly 100
        total = sum(pcts)
        if total == 0:
            return
        normalized = [p / total * 100 for p in pcts]
        stages = [{"stage": f"s{i}", "budget_pct": p} for i, p in enumerate(normalized)]
        out = json.dumps({"funnel_map": {"stages": stages}})
        result = budget_rationality(inputs="test", outputs=out, expectations=None)
        assert result.value >= 0.99


class TestFunnelCoverageProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = funnel_coverage(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, text):
        result = funnel_coverage(inputs=text, outputs=text, expectations=None)
        assert result is not None


class TestTargetingQualityProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = targeting_quality(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "ad_set_name": st.text(min_size=1, max_size=10),
                    "demographics": st.just({"age_min": 18}),
                    "interests": st.just(["Tech"]),
                    "custom_audiences": st.just(["buyers"]),
                    "lookalike_audiences": st.just([]),
                }
            ),
            min_size=1,
            max_size=3,
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_full_targeting_always_1(self, specs):
        out = json.dumps({"targeting_specs": specs})
        result = targeting_quality(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0
