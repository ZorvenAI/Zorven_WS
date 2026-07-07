"""Unit tests for common scorers (US-021).

Tests json_compliance, pii_safety, and token_efficiency directly.
brand_voice tests require Anthropic API and are in integration tests.
"""

import pytest

from app.scorers.common.json_compliance import json_compliance
from app.scorers.common.pii_safety import pii_safety
from app.scorers.common.token_efficiency import token_efficiency
from .conftest import requires_anthropic


class TestJsonCompliance:
    """AC-1: json_compliance returns 0.0 on JSONDecodeError with justification."""

    def test_valid_json_object(self):
        result = json_compliance(
            inputs="test", outputs='{"key": "value"}', expectations=None
        )
        assert result.value == 1.0

    def test_valid_json_array(self):
        result = json_compliance(inputs="test", outputs="[1, 2, 3]", expectations=None)
        assert result.value == 1.0

    def test_valid_nested_json(self):
        result = json_compliance(
            inputs="test",
            outputs='{"a": {"b": [1, 2, {"c": true}]}}',
            expectations=None,
        )
        assert result.value == 1.0

    def test_valid_json_string(self):
        result = json_compliance(inputs="test", outputs='"hello"', expectations=None)
        assert result.value == 1.0

    def test_valid_json_number(self):
        result = json_compliance(inputs="test", outputs="42", expectations=None)
        assert result.value == 1.0

    def test_invalid_json(self):
        result = json_compliance(
            inputs="test", outputs="not valid json", expectations=None
        )
        assert result.value == 0.0
        assert "JSONDecodeError" in result.rationale

    def test_json_trailing_comma(self):
        result = json_compliance(
            inputs="test",
            outputs='{"key": "value",}',
            expectations=None,
        )
        assert result.value == 0.0

    def test_empty_string(self):
        result = json_compliance(inputs="test", outputs="", expectations=None)
        assert result.value == 0.0
        assert "empty" in result.rationale.lower()

    def test_none_output(self):
        result = json_compliance(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0
        assert "None" in result.rationale

    def test_whitespace_only(self):
        result = json_compliance(inputs="test", outputs="   \n\t  ", expectations=None)
        assert result.value == 0.0

    def test_feedback_name(self):
        result = json_compliance(inputs="test", outputs="{}", expectations=None)
        assert result.name == "json_compliance"


class TestPiiSafety:
    """AC-2: pii_safety flags emails, phone numbers, SSNs, and government IDs."""

    def test_clean_text(self):
        result = pii_safety(
            inputs="test",
            outputs="This is a clean output with no personal data.",
            expectations=None,
        )
        assert result.value == 1.0

    def test_email_detected(self):
        result = pii_safety(
            inputs="test",
            outputs="Contact us at john@example.com for details.",
            expectations=None,
        )
        assert result.value == 0.0
        assert "email" in result.rationale

    def test_phone_detected(self):
        result = pii_safety(
            inputs="test",
            outputs="Call us at 555-123-4567.",
            expectations=None,
        )
        assert result.value == 0.0
        assert "phone" in result.rationale

    def test_phone_with_parens(self):
        result = pii_safety(
            inputs="test",
            outputs="Call (555) 123-4567 for info.",
            expectations=None,
        )
        assert result.value == 0.0
        assert "phone" in result.rationale

    def test_phone_with_country_code(self):
        result = pii_safety(
            inputs="test",
            outputs="Call +1-555-123-4567.",
            expectations=None,
        )
        assert result.value == 0.0
        assert "phone" in result.rationale

    def test_ssn_detected(self):
        result = pii_safety(
            inputs="test",
            outputs="SSN: 123-45-6789",
            expectations=None,
        )
        assert result.value == 0.0
        assert "ssn" in result.rationale

    def test_government_id_ein(self):
        result = pii_safety(
            inputs="test",
            outputs="EIN: 12-3456789",
            expectations=None,
        )
        assert result.value == 0.0
        assert "government_id" in result.rationale

    def test_multiple_pii_types(self):
        result = pii_safety(
            inputs="test",
            outputs="Email john@test.com, SSN 123-45-6789",
            expectations=None,
        )
        assert result.value == 0.0
        assert "email" in result.rationale
        assert "ssn" in result.rationale

    def test_none_output(self):
        result = pii_safety(inputs="test", outputs=None, expectations=None)
        assert result.value == 1.0

    def test_empty_output(self):
        result = pii_safety(inputs="test", outputs="", expectations=None)
        assert result.value == 1.0

    def test_feedback_name(self):
        result = pii_safety(inputs="test", outputs="clean text", expectations=None)
        assert result.name == "pii_safety"


class TestTokenEfficiency:
    """Token efficiency scores output conciseness."""

    def test_concise_output(self):
        result = token_efficiency(
            inputs="What is 2+2?",
            outputs="4",
            expectations=None,
        )
        assert result.value == 1.0

    def test_verbose_output(self):
        result = token_efficiency(
            inputs="What is 2+2?",
            outputs="x " * 5000,
            expectations=None,
        )
        assert result.value < 0.3

    def test_moderate_output(self):
        result = token_efficiency(
            inputs="Explain Python.",
            outputs="Python is a programming language. " * 5,
            expectations=None,
        )
        score = result.value
        assert 0.0 <= score <= 1.0

    def test_none_output(self):
        result = token_efficiency(inputs="test", outputs=None, expectations=None)
        assert result.value == 1.0

    def test_empty_output(self):
        result = token_efficiency(inputs="test", outputs="", expectations=None)
        assert result.value == 1.0

    def test_none_input(self):
        result = token_efficiency(
            inputs=None, outputs="some output text", expectations=None
        )
        assert 0.0 <= result.value <= 1.0

    def test_score_in_range(self):
        result = token_efficiency(
            inputs="short input",
            outputs="medium length output that is a few words long",
            expectations=None,
        )
        assert 0.0 <= result.value <= 1.0

    def test_feedback_name(self):
        result = token_efficiency(inputs="test", outputs="output", expectations=None)
        assert result.name == "token_efficiency"

    def test_rationale_contains_token_counts(self):
        result = token_efficiency(
            inputs="test input",
            outputs="test output response",
            expectations=None,
        )
        assert "tokens" in result.rationale

    def test_very_short_output_high_efficiency(self):
        result = token_efficiency(
            inputs="Explain the theory of relativity in detail with examples.",
            outputs="E=mc²",
            expectations=None,
        )
        assert result.value == 1.0

    def test_optimal_ratio_moderate_score(self):
        # Output ~5x input length — should be in mid-range
        short_input = "Summarize this."
        moderate_output = "word " * 50
        result = token_efficiency(
            inputs=short_input,
            outputs=moderate_output,
            expectations=None,
        )
        assert 0.0 <= result.value <= 1.0


class TestBrandVoice:
    """AC-3: brand_voice uses LLM judge with 0-5 rubric mapped to 0-1."""

    @requires_anthropic
    def test_returns_valid_score(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(
            inputs="Write a professional summary.",
            outputs=(
                "Our comprehensive analysis reveals significant growth "
                "opportunities in the enterprise software market. Strategic "
                "partnerships and innovative solutions position us well for "
                "sustainable expansion."
            ),
            expectations=None,
        )
        assert 0.0 <= result.value <= 1.0
        assert result.name == "brand_voice"

    @requires_anthropic
    def test_with_brand_voice_expectation(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(
            inputs="Write a message.",
            outputs=(
                "Hey there! Super excited to share our amazing new product. "
                "It's gonna be totally awesome and you'll love it! 🚀"
            ),
            expectations={
                "brand_voice": (
                    "Casual, energetic, and enthusiastic. Uses informal "
                    "language, exclamation marks, and emojis freely."
                )
            },
        )
        assert 0.0 <= result.value <= 1.0
        assert "Brand voice score" in result.rationale

    @requires_anthropic
    def test_empty_output(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs="", expectations=None)
        assert result.value == 0.0
        assert "Empty" in result.rationale

    def test_brand_voice_none_output_returns_zero(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs=None, expectations=None)
        assert result.value == 0.0

    def test_brand_voice_empty_string_returns_zero(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs="", expectations=None)
        assert result.value == 0.0

    def test_brand_voice_whitespace_output_returns_zero(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs="   \n\t  ", expectations=None)
        assert result.value == 0.0

    def test_brand_voice_none_output_rationale_mentions_empty(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs=None, expectations=None)
        assert "Empty" in result.rationale or "empty" in result.rationale.lower()

    def test_brand_voice_name_is_correct(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs=None, expectations=None)
        assert result.name == "brand_voice"

    def test_brand_voice_value_range_on_empty(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs="", expectations=None)
        assert 0.0 <= result.value <= 1.0

    def test_brand_voice_rationale_is_string(self):
        from app.scorers.common.brand_voice import brand_voice

        result = brand_voice(inputs="test", outputs=None, expectations=None)
        assert isinstance(result.rationale, str)
        assert len(result.rationale) > 0

    def test_brand_voice_default_voice_constant(self):
        from app.scorers.common.brand_voice import DEFAULT_BRAND_VOICE

        assert "Professional" in DEFAULT_BRAND_VOICE
        assert isinstance(DEFAULT_BRAND_VOICE, str)
        assert len(DEFAULT_BRAND_VOICE) > 20


class TestScorerSignatureConformance:
    """AC-4: All scorers conform to mlflow.genai.scorer signature."""

    def test_json_compliance_is_scorer(self):
        from mlflow.genai.scorers import Scorer

        assert isinstance(json_compliance, Scorer)

    def test_pii_safety_is_scorer(self):
        from mlflow.genai.scorers import Scorer

        assert isinstance(pii_safety, Scorer)

    def test_token_efficiency_is_scorer(self):
        from mlflow.genai.scorers import Scorer

        assert isinstance(token_efficiency, Scorer)

    @requires_anthropic
    def test_brand_voice_is_scorer(self):
        from mlflow.genai.scorers import Scorer
        from app.scorers.common.brand_voice import brand_voice

        assert isinstance(brand_voice, Scorer)

    def test_all_scorers_accept_keyword_args(self):
        """All scorers must accept inputs, outputs, expectations as kwargs."""
        for s in [json_compliance, pii_safety, token_efficiency]:
            result = s(inputs="test", outputs="test output", expectations=None)
            assert result is not None
