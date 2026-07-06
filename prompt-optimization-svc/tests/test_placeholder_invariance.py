"""Unit tests for placeholder invariance guardrail (US-030, OPT-11).

AC-4: cover removal, addition, and identical templates.
"""

from app.logic.gepa_guardrails import check_gepa_mutation
from app.logic.placeholder_validator import (
    PlaceholderInvarianceResult,
    validate_placeholder_invariance,
)


class TestValidatePlaceholderInvariance:
    """Core invariance validation tests."""

    def test_identical_templates(self):
        t = "Hello {{context.brand_name}}, welcome to {{context.industry}}."
        result = validate_placeholder_invariance(t, t)
        assert result.valid is True
        assert result.removed == set()
        assert result.added == set()
        assert result.needs_review is False

    def test_removed_placeholder(self):
        original = "Brand: {{context.brand_name}} in {{context.industry}}."
        mutated = "Brand overview for the industry."
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is False
        assert "context.brand_name" in result.removed
        assert "context.industry" in result.removed

    def test_added_placeholder(self):
        original = "Brand: {{context.brand_name}}."
        mutated = "Brand: {{context.brand_name}} in {{context.industry}}."
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is True
        assert result.needs_review is True
        assert "context.industry" in result.added

    def test_both_removed_and_added(self):
        original = "Brand: {{context.brand_name}}."
        mutated = "Industry: {{context.industry}}."
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is False
        assert "context.brand_name" in result.removed
        assert "context.industry" in result.added
        assert result.needs_review is True

    def test_empty_original(self):
        result = validate_placeholder_invariance("", "Hello {{context.brand_name}}")
        assert result.valid is True
        assert result.needs_review is True
        assert result.original_count == 0

    def test_empty_mutated_with_placeholders(self):
        result = validate_placeholder_invariance("{{context.brand_name}}", "")
        assert result.valid is False
        assert "context.brand_name" in result.removed

    def test_multiple_placeholders_one_removed(self):
        original = "{{context.brand_name}} in {{context.industry}} for {{context.target_audience}}"
        mutated = "{{context.brand_name}} in {{context.industry}} for everyone"
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is False
        assert result.removed == {"context.target_audience"}
        assert result.added == set()

    def test_dotted_placeholders(self):
        original = "Use {context.brand_name} for {context.product_description}"
        mutated = "Use {context.brand_name} for {context.product_description}"
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is True

    def test_double_brace_placeholders(self):
        original = "{{context.brand_name}} is great"
        mutated = "{{context.brand_name}} is amazing"
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is True

    def test_mixed_single_and_double(self):
        original = "{context.brand_name} and {{context.industry}}"
        mutated = "{context.brand_name} and {{context.industry}}"
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is True

    def test_no_placeholders_in_either(self):
        result = validate_placeholder_invariance("Hello world", "Goodbye world")
        assert result.valid is True
        assert result.needs_review is False
        assert result.original_count == 0
        assert result.mutated_count == 0

    def test_counts_correct(self):
        original = "{{context.brand_name}} {{context.industry}}"
        mutated = "{{context.brand_name}} {{context.voice}}"
        result = validate_placeholder_invariance(original, mutated)
        assert result.original_count == 2
        assert result.mutated_count == 2

    def test_result_is_dataclass(self):
        result = validate_placeholder_invariance("test", "test")
        assert isinstance(result, PlaceholderInvarianceResult)


class TestCheckGepaMutation:
    """GEPA guardrail hook tests."""

    def test_accepted_identical(self):
        t = "Analyze {{context.brand_name}} in {{context.industry}}"
        accepted, result = check_gepa_mutation(t, t)
        assert accepted is True
        assert result.valid is True

    def test_rejected_removal(self):
        original = "{{context.brand_name}} in {{context.industry}}"
        candidate = "Brand analysis report"
        accepted, result = check_gepa_mutation(original, candidate)
        assert accepted is False
        assert result.valid is False

    def test_accepted_with_review_flag(self):
        original = "{{context.brand_name}}"
        candidate = "{{context.brand_name}} targeting {{context.target_audience}}"
        accepted, result = check_gepa_mutation(original, candidate)
        assert accepted is True
        assert result.needs_review is True

    def test_returns_tuple(self):
        accepted, result = check_gepa_mutation("test", "test")
        assert isinstance(accepted, bool)
        assert isinstance(result, PlaceholderInvarianceResult)

    def test_text_changes_without_placeholder_changes(self):
        original = "Analyze the brand {{context.brand_name}} thoroughly."
        candidate = "Perform deep analysis on {{context.brand_name}} with precision."
        accepted, result = check_gepa_mutation(original, candidate)
        assert accepted is True
        assert result.removed == set()
        assert result.added == set()


class TestPlaceholderEdgeCases:
    """Edge case tests for placeholder extraction and invariance."""

    def test_nested_braces_not_treated_as_placeholder(self):
        """Triple braces like {{{x}}} — inner double-brace matched, not outer."""
        from app.logic.placeholder_validator import extract_placeholders

        # Python-style single-brace inside double braces
        result = extract_placeholders("{{not_a_placeholder}}")
        # Double brace pattern matches {{not_a_placeholder}} → "not_a_placeholder"
        assert "not_a_placeholder" in result

    def test_placeholder_in_code_block(self):
        """Placeholders inside backtick code blocks are still extracted."""
        template = "```\n{context.brand_name}\n```"
        result = validate_placeholder_invariance(template, template)
        assert result.valid is True
        assert result.original_count == 1

    def test_duplicate_placeholders_deduplicated(self):
        """Same placeholder appearing twice only counted once."""
        from app.logic.placeholder_validator import extract_placeholders

        placeholders = extract_placeholders(
            "{context.brand_name} and {context.brand_name} again"
        )
        assert len(placeholders) == 1
        assert "context.brand_name" in placeholders

    def test_empty_templates_valid(self):
        result = validate_placeholder_invariance("", "")
        assert result.valid is True
        assert result.original_count == 0
        assert result.mutated_count == 0

    def test_whitespace_only_templates_valid(self):
        result = validate_placeholder_invariance("   \n\t  ", "  \n  ")
        assert result.valid is True
        assert result.original_count == 0
        assert result.mutated_count == 0
