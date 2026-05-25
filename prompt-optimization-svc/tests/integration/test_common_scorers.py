"""Integration tests for common scorers (US-021).

Requires real Anthropic API and MLflow.
"""

import pytest

from tests.conftest import requires_anthropic


@requires_anthropic
class TestBrandVoiceIntegration:
    """brand_voice scorer with real Anthropic API."""

    def test_professional_text_scores_well(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(
            inputs="Write a quarterly business update.",
            outputs=(
                "Our Q3 results demonstrate robust growth across all key "
                "metrics. Revenue increased 15% year-over-year, driven by "
                "strategic expansion into enterprise markets and strong "
                "customer retention rates."
            ),
            expectations={
                "brand_voice": (
                    "Professional, data-driven, and confident. "
                    "Uses precise metrics and business terminology."
                )
            },
        )
        assert 0.0 <= result.value <= 1.0
        assert result.name == "brand_voice"
        assert "Brand voice score" in result.rationale

    def test_mismatched_voice_scores_lower(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(
            inputs="Write a formal legal notice.",
            outputs=(
                "yo whats up!! just wanted to let u know that like, "
                "we're totally changing some stuff lol 😂 dont worry bout it"
            ),
            expectations={
                "brand_voice": (
                    "Formal, precise, and legally authoritative. "
                    "Uses legal terminology and structured language."
                )
            },
        )
        assert 0.0 <= result.value <= 1.0
        # Informal text against formal expectation should score relatively low
        assert result.value < 0.8

    def test_default_voice_returns_valid_feedback(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(
            inputs="test",
            outputs="This is a clear and professional response.",
            expectations=None,
        )
        assert 0.0 <= result.value <= 1.0
        assert result.rationale is not None


@requires_anthropic
class TestScorerEndToEnd:
    """End-to-end test with all four scorers using real Anthropic."""

    def test_all_four_scorers_produce_valid_feedback(self):
        from app.scorers import COMMON_SCORERS

        test_input = "Write a professional product description."
        test_output = (
            '{"title": "Premium Widget", "description": "A high-quality widget."}'
        )

        for s in COMMON_SCORERS:
            result = s(
                inputs=test_input,
                outputs=test_output,
                expectations={"brand_voice": "Professional and product-focused."},
            )
            assert result is not None
            assert 0.0 <= result.value <= 1.0
            assert result.rationale is not None
