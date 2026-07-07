"""Hypothesis property tests for template-context separation (US-016)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.logic.placeholder_validator import extract_placeholders, validate_template_placeholders
from app.services.context_builder import build_context_from_onboarding

_plain_text = st.text(min_size=0, max_size=200, alphabet="abcdefghijklmnopqrstuvwxyz 0123456789.,!?")
_context_var = st.from_regex(r"context\.[a-z_]{1,15}", fullmatch=True)


class TestExtractPlaceholdersProperties:

    @given(text=_plain_text)
    @hyp_settings(max_examples=50)
    def test_plain_text_returns_empty(self, text):
        """Text without braces yields empty set."""
        if "{" not in text and "}" not in text:
            assert extract_placeholders(text) == set()

    @given(var=_context_var)
    @hyp_settings(max_examples=30)
    def test_single_brace_extracted(self, var):
        result = extract_placeholders(f"prefix {{{var}}} suffix")
        assert var in result

    @given(var=_context_var)
    @hyp_settings(max_examples=30)
    def test_double_brace_extracted(self, var):
        result = extract_placeholders(f"prefix {{{{{var}}}}} suffix")
        assert var in result

    @given(var=_context_var)
    @hyp_settings(max_examples=20)
    def test_all_extracted_contain_dot(self, var):
        result = extract_placeholders(f"{{{var}}}")
        for ph in result:
            assert "." in ph


class TestValidateTemplateProperties:

    @given(var=_context_var)
    @hyp_settings(max_examples=30)
    def test_context_vars_always_valid(self, var):
        """Any {context.*} placeholder passes validation."""
        violations = validate_template_placeholders(f"{{{var}}}")
        assert violations == []

    @given(var=st.from_regex(r"[a-z]{3,10}", fullmatch=True))
    @hyp_settings(max_examples=30)
    def test_non_context_vars_rejected(self, var):
        """Placeholders without context. prefix are rejected."""
        if not var.startswith("context."):
            violations = validate_template_placeholders(f"{{{var}}}")
            assert len(violations) >= 1


class TestBuildContextProperties:

    @given(
        brand=st.text(min_size=1, max_size=50),
        industry=st.text(min_size=1, max_size=50),
    )
    @hyp_settings(max_examples=50)
    def test_all_keys_start_with_context(self, brand, industry):
        """Output keys always start with context."""
        ctx = build_context_from_onboarding(
            {"brand_name": brand, "industry": industry}
        )
        for key in ctx:
            assert key.startswith("context."), f"Key {key} missing context. prefix"

    @given(
        brand=st.text(min_size=1, max_size=50),
        budget=st.integers(),
        items=st.lists(st.text(min_size=1), max_size=3),
    )
    @hyp_settings(max_examples=30)
    def test_all_values_are_strings(self, brand, budget, items):
        """All output values are strings."""
        ctx = build_context_from_onboarding(
            {"brand_name": brand},
            runtime_data={"budget": budget, "items": items},
        )
        for key, value in ctx.items():
            assert isinstance(value, str), f"{key} is {type(value).__name__}"

    @given(brand=st.text(min_size=1, max_size=50))
    @hyp_settings(max_examples=20)
    def test_none_values_excluded(self, brand):
        """None values never appear in output."""
        ctx = build_context_from_onboarding(
            {"brand_name": brand},
            runtime_data={"query": None, "budget": None},
        )
        for key, value in ctx.items():
            assert value != "None", f"{key} has stringified None"
