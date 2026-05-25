"""Unit tests for CGA scorers (US-022).

AC-6: 10+ unit tests per scorer covering perfect, partial, invalid, and edge inputs.
"""

import json

import pytest

from app.scorers.cga.character_limits import character_limits
from app.scorers.cga.creative_compliance import creative_compliance
from app.scorers.cga.cta_effectiveness import cta_effectiveness
from app.scorers.cga.variant_diversity import variant_diversity
from .conftest import requires_anthropic


def _cga_output(**overrides) -> str:
    """Build a minimal valid CGA output JSON string."""
    data = {
        "hooks": overrides.get(
            "hooks",
            [
                {
                    "hook_text": "Boost your brand today",
                    "funnel_stage": "tofu",
                    "hook_type": "urgency",
                    "char_count": 21,
                },
                {
                    "hook_text": "Discover new growth",
                    "funnel_stage": "mofu",
                    "hook_type": "curiosity",
                    "char_count": 19,
                },
            ],
        ),
        "copy_variants": overrides.get(
            "copy_variants",
            [
                {
                    "copy_text": "Short ad copy here.",
                    "funnel_stage": "tofu",
                    "length_label": "short",
                    "char_count": 19,
                    "voice_consistency": 85,
                    "positioning_alignment": 90,
                },
                {
                    "copy_text": "Another variant of copy.",
                    "funnel_stage": "mofu",
                    "length_label": "short",
                    "char_count": 24,
                    "voice_consistency": 80,
                    "positioning_alignment": 85,
                },
            ],
        ),
        "ctas": overrides.get(
            "ctas",
            [
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "Learn More",
                    "funnel_stage": "tofu",
                    "urgency_score": 60,
                    "clarity_score": 90,
                },
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "bofu",
                    "urgency_score": 85,
                    "clarity_score": 95,
                },
            ],
        ),
        "compliance_results": overrides.get(
            "compliance_results",
            [
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "pass",
                    "violations": [],
                },
                {
                    "variant_id": "c1",
                    "variant_type": "copy",
                    "status": "pass",
                    "violations": [],
                },
            ],
        ),
    }
    data.update({k: v for k, v in overrides.items() if k not in data})
    return json.dumps(data)


# ── creative_compliance tests (AC-1) ──


class TestCreativeCompliance:
    """AC-1: enforces JSON validity and required fields."""

    def test_all_pass(self):
        result = creative_compliance(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert result.value == 1.0

    def test_all_fail(self):
        out = _cga_output(
            compliance_results=[
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "fail",
                    "violations": [{"rule": "x"}],
                },
                {
                    "variant_id": "c1",
                    "variant_type": "copy",
                    "status": "fail",
                    "violations": [{"rule": "y"}],
                },
            ]
        )
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_mixed_pass_fail(self):
        out = _cga_output(
            compliance_results=[
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "pass",
                    "violations": [],
                },
                {
                    "variant_id": "c1",
                    "variant_type": "copy",
                    "status": "fail",
                    "violations": [{"rule": "x"}],
                },
            ]
        )
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert 0.0 < result.value < 1.0

    def test_warnings_partial_credit(self):
        out = _cga_output(
            compliance_results=[
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "warning",
                    "violations": [],
                },
                {
                    "variant_id": "c1",
                    "variant_type": "copy",
                    "status": "warning",
                    "violations": [],
                },
            ]
        )
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.5

    def test_missing_required_fields(self):
        result = creative_compliance(
            inputs="test", outputs='{"hooks": []}', expectations=None
        )
        assert result.value == 0.0
        assert "Missing required" in result.rationale

    def test_invalid_json(self):
        result = creative_compliance(
            inputs="test", outputs="not json", expectations=None
        )
        assert result.value == 0.0

    def test_none_output(self):
        result = creative_compliance(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_empty_compliance_results(self):
        out = _cga_output(compliance_results=[])
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_single_pass(self):
        out = _cga_output(
            compliance_results=[
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "pass",
                    "violations": [],
                }
            ]
        )
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_single_fail(self):
        out = _cga_output(
            compliance_results=[
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "fail",
                    "violations": [],
                }
            ]
        )
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = creative_compliance(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert result.name == "creative_compliance"

    def test_dict_input(self):
        data = json.loads(_cga_output())
        result = creative_compliance(inputs="test", outputs=data, expectations=None)
        assert result.value == 1.0


# ── character_limits tests (AC-2) ──


class TestCharacterLimits:
    """AC-2: enforces 40/125/30 char rules with zero-tolerance >10 char overflow."""

    def test_all_within_limits(self):
        result = character_limits(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert result.value == 1.0

    def test_hook_over_40(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "A" * 45,
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 45,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_hook_zero_tolerance(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "A" * 55,
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 55,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0
        assert "Zero-tolerance" in result.rationale

    def test_cta_over_30(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "A" * 35,
                    "funnel_stage": "bofu",
                    "urgency_score": 80,
                    "clarity_score": 90,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_cta_zero_tolerance(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "A" * 45,
                    "funnel_stage": "bofu",
                    "urgency_score": 80,
                    "clarity_score": 90,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_copy_short_over_125(self):
        out = _cga_output(
            copy_variants=[
                {
                    "copy_text": "A" * 130,
                    "funnel_stage": "tofu",
                    "length_label": "short",
                    "char_count": 130,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0

    def test_copy_short_zero_tolerance(self):
        out = _cga_output(
            copy_variants=[
                {
                    "copy_text": "A" * 140,
                    "funnel_stage": "tofu",
                    "length_label": "short",
                    "char_count": 140,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_exactly_at_limit(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "A" * 40,
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 40,
                }
            ],
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "A" * 30,
                    "funnel_stage": "bofu",
                    "urgency_score": 80,
                    "clarity_score": 90,
                }
            ],
            copy_variants=[
                {
                    "copy_text": "A" * 125,
                    "funnel_stage": "tofu",
                    "length_label": "short",
                    "char_count": 125,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                }
            ],
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_none_output(self):
        result = character_limits(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_empty_output(self):
        result = character_limits(inputs="test", outputs="{}", expectations=None)
        assert result.value == 0.0

    def test_mixed_compliance(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "Short",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 5,
                },
                {
                    "hook_text": "A" * 45,
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 45,
                },
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert 0.0 < result.value < 1.0

    def test_feedback_name(self):
        result = character_limits(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert result.name == "character_limits"


# ── variant_diversity tests (AC-3) ──


class TestVariantDiversity:
    """AC-3: computes cosine similarity over variant texts."""

    def test_identical_variants(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "Same hook text",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 14,
                },
                {
                    "hook_text": "Same hook text",
                    "funnel_stage": "mofu",
                    "hook_type": "x",
                    "char_count": 14,
                },
            ],
            copy_variants=[],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value < 0.1

    def test_completely_different_variants(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "Boost your brand with AI power",
                    "funnel_stage": "tofu",
                    "hook_type": "urgency",
                    "char_count": 30,
                },
                {
                    "hook_text": "Transform digital marketing",
                    "funnel_stage": "mofu",
                    "hook_type": "curiosity",
                    "char_count": 27,
                },
            ],
            copy_variants=[
                {
                    "copy_text": "Revolutionary platform for growth",
                    "funnel_stage": "tofu",
                    "length_label": "short",
                    "char_count": 33,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                },
                {
                    "copy_text": "Enterprise solutions that scale",
                    "funnel_stage": "mofu",
                    "length_label": "short",
                    "char_count": 31,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                },
            ],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.3

    def test_single_variant(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "Only one hook",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 13,
                }
            ],
            copy_variants=[],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_two_moderately_different(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "Get amazing deals today",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 23,
                },
                {
                    "hook_text": "Get incredible offers now",
                    "funnel_stage": "mofu",
                    "hook_type": "x",
                    "char_count": 25,
                },
            ],
            copy_variants=[],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert 0.0 < result.value < 1.0

    def test_none_output(self):
        result = variant_diversity(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_only_hooks(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "First hook text",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 15,
                },
                {
                    "hook_text": "Completely different second",
                    "funnel_stage": "mofu",
                    "hook_type": "y",
                    "char_count": 26,
                },
            ],
            copy_variants=[],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.0

    def test_score_in_range(self):
        result = variant_diversity(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert 0.0 <= result.value <= 1.0

    def test_deterministic(self):
        out = _cga_output()
        r1 = variant_diversity(inputs="test", outputs=out, expectations=None)
        r2 = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert r1.value == r2.value

    def test_empty_strings_handled(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 0,
                },
                {
                    "hook_text": "",
                    "funnel_stage": "mofu",
                    "hook_type": "x",
                    "char_count": 0,
                },
            ],
            copy_variants=[],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0  # empty texts filtered out

    def test_feedback_name(self):
        result = variant_diversity(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert result.name == "variant_diversity"

    def test_unicode_text(self):
        out = _cga_output(
            hooks=[
                {
                    "hook_text": "日本語のテキスト",
                    "funnel_stage": "tofu",
                    "hook_type": "x",
                    "char_count": 8,
                },
                {
                    "hook_text": "中文广告文案",
                    "funnel_stage": "mofu",
                    "hook_type": "x",
                    "char_count": 6,
                },
            ],
            copy_variants=[],
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert 0.0 <= result.value <= 1.0


# ── brand_voice_match tests (AC-4) ──


class TestBrandVoiceMatch:
    """AC-4: LLM judge scored 0-5."""

    def test_empty_output(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        result = brand_voice_match(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_no_copy_in_output(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        out = _cga_output(hooks=[], copy_variants=[])
        result = brand_voice_match(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0
        assert "No ad copy" in result.rationale

    def test_feedback_name(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        result = brand_voice_match(inputs="test", outputs=None, expectations=None)
        assert result.name == "brand_voice_match"

    @requires_anthropic
    def test_returns_valid_score(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        result = brand_voice_match(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert 0.0 <= result.value <= 1.0

    @requires_anthropic
    def test_with_custom_voice(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        result = brand_voice_match(
            inputs="test",
            outputs=_cga_output(),
            expectations={"brand_voice": "Casual, youthful, and energetic."},
        )
        assert 0.0 <= result.value <= 1.0
        assert "Brand voice score" in result.rationale


# ── cta_effectiveness tests (AC-5) ──


class TestCtaEffectiveness:
    """AC-5: rule-based action verb and urgency detection."""

    def test_strong_ctas(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "Learn More Now",
                    "funnel_stage": "tofu",
                    "urgency_score": 80,
                    "clarity_score": 90,
                },
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "bofu",
                    "urgency_score": 90,
                    "clarity_score": 95,
                },
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.6

    def test_no_action_verb(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "More info here",
                    "funnel_stage": "tofu",
                    "urgency_score": 50,
                    "clarity_score": 60,
                },
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value < 0.8

    def test_urgency_words_bonus(self):
        out_with = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now - Limited Time",
                    "funnel_stage": "bofu",
                    "urgency_score": 90,
                    "clarity_score": 90,
                }
            ]
        )
        out_without = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop here please",
                    "funnel_stage": "bofu",
                    "urgency_score": 50,
                    "clarity_score": 90,
                }
            ]
        )
        r_with = cta_effectiveness(inputs="test", outputs=out_with, expectations=None)
        r_without = cta_effectiveness(
            inputs="test", outputs=out_without, expectations=None
        )
        assert r_with.value >= r_without.value

    def test_tofu_learn_more_aligned(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "Learn More",
                    "funnel_stage": "tofu",
                    "urgency_score": 60,
                    "clarity_score": 90,
                }
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.5

    def test_bofu_learn_more_misaligned(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "Learn More",
                    "funnel_stage": "bofu",
                    "urgency_score": 60,
                    "clarity_score": 90,
                }
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        # LEARN_MORE not in BOFU set, alignment penalty
        aligned_out = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "bofu",
                    "urgency_score": 60,
                    "clarity_score": 90,
                }
            ]
        )
        aligned_result = cta_effectiveness(
            inputs="test", outputs=aligned_out, expectations=None
        )
        assert result.value < aligned_result.value

    def test_high_clarity_urgency_scores(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "bofu",
                    "urgency_score": 95,
                    "clarity_score": 98,
                }
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.7

    def test_none_output(self):
        result = cta_effectiveness(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_no_ctas(self):
        out = _cga_output(ctas=[])
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_mixed_quality(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "bofu",
                    "urgency_score": 90,
                    "clarity_score": 95,
                },
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "Click here",
                    "funnel_stage": "bofu",
                    "urgency_score": 20,
                    "clarity_score": 30,
                },
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert 0.0 < result.value < 1.0

    def test_feedback_has_breakdown(self):
        out = _cga_output()
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert "CTAs evaluated" in result.rationale
        assert "Action verbs" in result.rationale

    def test_feedback_name(self):
        result = cta_effectiveness(
            inputs="test", outputs=_cga_output(), expectations=None
        )
        assert result.name == "cta_effectiveness"

    def test_retention_funnel(self):
        out = _cga_output(
            ctas=[
                {
                    "cta_button": "SHOP_NOW",
                    "cta_text": "Shop Now",
                    "funnel_stage": "retention",
                    "urgency_score": 80,
                    "clarity_score": 85,
                }
            ]
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value > 0.5


# ── Scorer signature conformance (AC-6) ──


class TestScorerConformance:
    """All CGA scorers conform to mlflow.genai.scorer signature."""

    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        for s in [
            creative_compliance,
            character_limits,
            variant_diversity,
            cta_effectiveness,
        ]:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_all_accept_keyword_args(self):
        for s in [
            creative_compliance,
            character_limits,
            variant_diversity,
            cta_effectiveness,
        ]:
            result = s(inputs="test", outputs=_cga_output(), expectations=None)
            assert result is not None


class TestMalformedInputRobustness:
    """All scorers handle malformed-but-valid JSON without crashing."""

    def test_creative_compliance_string_results(self):
        out = json.dumps(
            {
                "hooks": [],
                "copy_variants": [],
                "ctas": [],
                "compliance_results": "pass",
            }
        )
        result = creative_compliance(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_character_limits_string_hooks(self):
        out = json.dumps(
            {
                "hooks": "bad",
                "copy_variants": [],
                "ctas": [],
                "compliance_results": [],
            }
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_variant_diversity_string_hooks(self):
        out = json.dumps(
            {
                "hooks": "bad",
                "copy_variants": [],
                "ctas": [],
                "compliance_results": [],
            }
        )
        result = variant_diversity(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_cta_effectiveness_string_ctas(self):
        out = json.dumps(
            {
                "hooks": [],
                "copy_variants": [],
                "ctas": "bad",
                "compliance_results": [],
            }
        )
        result = cta_effectiveness(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_brand_voice_match_string_hooks(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        out = json.dumps(
            {
                "hooks": "bad",
                "copy_variants": [],
                "ctas": [],
                "compliance_results": [],
            }
        )
        result = brand_voice_match(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_character_limits_non_dict_items(self):
        out = json.dumps(
            {
                "hooks": ["not a dict", 42],
                "copy_variants": [None],
                "ctas": [True],
                "compliance_results": [],
            }
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 0.0

    def test_character_limits_long_copy(self):
        """Long copy variant uses 500 char limit."""
        out = _cga_output(
            copy_variants=[
                {
                    "copy_text": "A" * 450,
                    "funnel_stage": "bofu",
                    "length_label": "long",
                    "char_count": 450,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value == 1.0

    def test_character_limits_medium_over_200(self):
        """Medium copy variant uses 200 char limit."""
        out = _cga_output(
            copy_variants=[
                {
                    "copy_text": "A" * 205,
                    "funnel_stage": "mofu",
                    "length_label": "medium",
                    "char_count": 205,
                    "voice_consistency": 80,
                    "positioning_alignment": 80,
                }
            ]
        )
        result = character_limits(inputs="test", outputs=out, expectations=None)
        assert result.value < 1.0
