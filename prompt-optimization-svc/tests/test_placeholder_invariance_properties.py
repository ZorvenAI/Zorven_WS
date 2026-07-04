"""Hypothesis property tests for placeholder invariance (US-030)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.placeholder_validator import validate_placeholder_invariance


class TestInvarianceProperties:
    @given(st.text(max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_identical_always_valid(self, template):
        result = validate_placeholder_invariance(template, template)
        assert result.valid is True
        assert result.removed == set()
        assert result.added == set()

    @given(st.text(max_size=100), st.text(max_size=100))
    @settings(max_examples=50, deadline=None)
    def test_removed_union_added_equals_symmetric_diff(self, t1, t2):
        from app.logic.placeholder_validator import extract_placeholders

        result = validate_placeholder_invariance(t1, t2)
        orig = extract_placeholders(t1)
        mut = extract_placeholders(t2)
        assert result.removed == orig - mut
        assert result.added == mut - orig

    @given(st.text(max_size=100))
    @settings(max_examples=50, deadline=None)
    def test_superset_always_valid(self, extra_text):
        original = "Use {{context.brand_name}} for analysis."
        mutated = f"Use {{{{context.brand_name}}}} for analysis. {extra_text}"
        result = validate_placeholder_invariance(original, mutated)
        assert result.valid is True

    @given(st.text(max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, template):
        result = validate_placeholder_invariance(template, "")
        assert isinstance(result.valid, bool)

    @given(st.text(max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_counts_non_negative(self, template):
        result = validate_placeholder_invariance(template, template)
        assert result.original_count >= 0
        assert result.mutated_count >= 0
