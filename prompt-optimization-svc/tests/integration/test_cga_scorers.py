"""Integration tests for CGA scorers (US-022).

Requires real Anthropic API and/or MLflow.
"""

import json

from tests.conftest import requires_anthropic, requires_mlflow


def _cga_output() -> str:
    return json.dumps(
        {
            "hooks": [
                {
                    "hook_text": "Boost your brand today",
                    "funnel_stage": "tofu",
                    "hook_type": "urgency",
                    "char_count": 21,
                },
                {
                    "hook_text": "Discover growth secrets",
                    "funnel_stage": "mofu",
                    "hook_type": "curiosity",
                    "char_count": 23,
                },
            ],
            "copy_variants": [
                {
                    "copy_text": "Professional ad copy.",
                    "funnel_stage": "tofu",
                    "length_label": "short",
                    "char_count": 20,
                    "voice_consistency": 85,
                    "positioning_alignment": 90,
                },
            ],
            "ctas": [
                {
                    "cta_button": "LEARN_MORE",
                    "cta_text": "Learn More",
                    "funnel_stage": "tofu",
                    "urgency_score": 60,
                    "clarity_score": 90,
                },
            ],
            "compliance_results": [
                {
                    "variant_id": "h1",
                    "variant_type": "hook",
                    "status": "pass",
                    "violations": [],
                },
            ],
        }
    )


@requires_anthropic
class TestBrandVoiceMatchIntegration:
    """brand_voice_match with real Anthropic API."""

    def test_returns_valid_score(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        result = brand_voice_match(
            inputs="test",
            outputs=_cga_output(),
            expectations={"brand_voice": "Professional and action-oriented."},
        )
        assert 0.0 <= result.value <= 1.0
        assert "Brand voice score" in result.rationale

    def test_with_custom_voice(self):
        from app.scorers.cga.brand_voice_match import brand_voice_match

        result = brand_voice_match(
            inputs="test",
            outputs=_cga_output(),
            expectations={"brand_voice": "Casual, fun, and youthful."},
        )
        assert 0.0 <= result.value <= 1.0


@requires_mlflow
class TestCgaScorerMlflowCompatibility:
    """Verify CGA scorers work with MLflow."""

    def test_all_are_scorer_instances(self):
        from mlflow.genai.scorers import Scorer

        from app.scorers.cga import CGA_SCORERS

        for s in CGA_SCORERS:
            assert isinstance(s, Scorer), f"{s.name} is not a Scorer"

    def test_cga_scorers_list_has_five(self):
        from app.scorers.cga import CGA_SCORERS

        assert len(CGA_SCORERS) == 5
        names = {s.name for s in CGA_SCORERS}
        assert names == {
            "creative_compliance",
            "character_limits",
            "variant_diversity",
            "brand_voice_match",
            "cta_effectiveness",
        }
