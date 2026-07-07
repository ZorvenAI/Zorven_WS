"""Hypothesis property-based tests for optimization guardrails (US-049)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.guardrails import (
    GuardrailResult,
    check_cost_cap,
    check_length_sanity,
    check_prompt_injection,
)


class TestCostCapProperties:
    @settings(max_examples=50, deadline=None)
    @given(cost=st.floats(min_value=0.0, max_value=24.99, allow_nan=False))
    def test_under_cap_always_passes(self, cost):
        result = check_cost_cap(cost, cap_usd=25.0)
        assert result.passed is True
        assert result.guardrail_id == "OPT-02"

    @settings(max_examples=50, deadline=None)
    @given(cost=st.floats(min_value=25.0, max_value=10000.0, allow_nan=False))
    def test_at_or_over_cap_always_fails(self, cost):
        result = check_cost_cap(cost, cap_usd=25.0)
        assert result.passed is False
        assert result.guardrail_id == "OPT-02"


class TestLengthSanityProperties:
    @settings(max_examples=50, deadline=None)
    @given(text=st.text(min_size=1, max_size=100))
    def test_same_text_always_passes(self, text):
        result = check_length_sanity(text, text, multiplier_limit=3.0)
        assert result.passed is True


class TestInjectionScanProperties:
    @settings(max_examples=50, deadline=None)
    @given(text=st.from_regex(r"[A-Za-z0-9 ,.!?]{1,200}", fullmatch=True))
    def test_alphanumeric_text_returns_opt09(self, text):
        result = check_prompt_injection(text)
        assert result.guardrail_id == "OPT-09"


class TestGuardrailResultProperties:
    @settings(max_examples=30, deadline=None)
    @given(
        passed=st.booleans(),
        gid=st.text(min_size=3, max_size=6),
        msg=st.text(max_size=100),
    )
    def test_always_has_required_fields(self, passed, gid, msg):
        r = GuardrailResult(passed=passed, guardrail_id=gid, message=msg)
        assert isinstance(r.passed, bool)
        assert isinstance(r.guardrail_id, str)
        assert isinstance(r.message, str)
        assert isinstance(r.details, dict)
