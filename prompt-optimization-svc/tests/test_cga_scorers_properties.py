"""Hypothesis property tests for CGA scorers (US-022)."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.scorers.cga.character_limits import character_limits
from app.scorers.cga.creative_compliance import creative_compliance
from app.scorers.cga.cta_effectiveness import cta_effectiveness
from app.scorers.cga.variant_diversity import variant_diversity


def _make_cga_json(**overrides) -> str:
    data = {
        "hooks": overrides.get("hooks", []),
        "copy_variants": overrides.get("copy_variants", []),
        "ctas": overrides.get("ctas", []),
        "compliance_results": overrides.get("compliance_results", []),
    }
    return json.dumps(data)


class TestCreativeComplianceProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = creative_compliance(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, text):
        result = creative_compliance(inputs=text, outputs=text, expectations=None)
        assert result is not None

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "variant_id": st.text(min_size=1, max_size=5),
                    "variant_type": st.sampled_from(["hook", "copy", "cta"]),
                    "status": st.just("pass"),
                    "violations": st.just([]),
                }
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_all_pass_scores_1(self, results):
        out = _make_cga_json(compliance_results=results)
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0


class TestCharacterLimitsProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = character_limits(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text(max_size=30))
    @settings(max_examples=50, deadline=None)
    def test_short_cta_always_passes(self, cta_text):
        out = _make_cga_json(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": cta_text,
                    "funnel_stage": "bofu",
                    "urgency_score": 80,
                    "clarity_score": 90,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0


class TestVariantDiversityProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = variant_diversity(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text(min_size=5, max_size=50))
    @settings(max_examples=30, deadline=None)
    def test_identical_texts_low_diversity(self, text):
        out = _make_cga_json(
            hooks=[
                {
                    "hook_text": text,
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": len(text),
                },
                {
                    "hook_text": text,
                    "funnel_stage": "mofu",
                    "hook_type": "x",
                    "char_count": len(text),
                },
            ]
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value <= 0.2


class TestCtaEffectivenessProperties:
    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = cta_effectiveness(inputs="test", outputs=text, expectations=None)
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text())
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, text):
        result = cta_effectiveness(inputs=text, outputs=text, expectations=None)
        assert result is not None

    def test_deterministic(self):
        out = _make_cga_json(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "bofu",
                    "urgency_score": 80,
                    "clarity_score": 90,
                }
            ]
        )
        r1 = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        r2 = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert r1.value == r2.value
