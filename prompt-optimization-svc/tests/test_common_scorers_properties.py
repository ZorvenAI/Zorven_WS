"""Hypothesis property tests for common scorers (US-021).

Verifies scorer invariants hold across random inputs.
"""

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.scorers.common.json_compliance import json_compliance
from app.scorers.common.pii_safety import pii_safety
from app.scorers.common.token_efficiency import token_efficiency


class TestJsonComplianceProperties:
    """Property-based tests for json_compliance scorer."""

    @given(st.text())
    @settings(max_examples=100, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = json_compliance(inputs="test", outputs=text, expectations=None)
        assert isinstance(result.value, (int, float))
        assert 0.0 <= float(result.value) <= 1.0

    @given(
        st.one_of(
            st.dictionaries(st.text(min_size=1), st.text()),
            st.lists(st.integers()),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none(),
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_valid_json_always_scores_1(self, value):
        json_str = json.dumps(value)
        result = json_compliance(inputs="test", outputs=json_str, expectations=None)
        assert result.value == 1.0

    @given(st.text())
    @settings(max_examples=100, deadline=None)
    def test_never_raises(self, text):
        # Should never raise, regardless of input
        result = json_compliance(inputs=text, outputs=text, expectations=None)
        assert result is not None

    @given(st.none())
    def test_none_always_scores_0(self, value):
        result = json_compliance(inputs="test", outputs=value, expectations=None)
        assert result.value == 0.0


class TestPiiSafetyProperties:
    """Property-based tests for pii_safety scorer."""

    @given(st.text())
    @settings(max_examples=100, deadline=None)
    def test_always_returns_float_in_range(self, text):
        result = pii_safety(inputs="test", outputs=text, expectations=None)
        assert isinstance(result.value, (int, float))
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.from_regex(r"[a-z]+@[a-z]+\.[a-z]{2,}", fullmatch=True))
    @settings(max_examples=50, deadline=None)
    def test_email_always_flagged(self, email):
        text = f"Contact {email} for details."
        result = pii_safety(inputs="test", outputs=text, expectations=None)
        assert result.value == 0.0

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz "))
    @settings(max_examples=100, deadline=None)
    def test_alphabetic_text_is_safe(self, text):
        result = pii_safety(inputs="test", outputs=text, expectations=None)
        assert result.value == 1.0

    @given(st.text())
    @settings(max_examples=100, deadline=None)
    def test_never_raises(self, text):
        result = pii_safety(inputs=text, outputs=text, expectations=None)
        assert result is not None


class TestTokenEfficiencyProperties:
    """Property-based tests for token_efficiency scorer."""

    @given(st.text(), st.text())
    @settings(max_examples=100, deadline=None)
    def test_always_returns_float_in_range(self, inp, out):
        result = token_efficiency(inputs=inp, outputs=out, expectations=None)
        assert isinstance(result.value, (int, float))
        assert 0.0 <= float(result.value) <= 1.0

    @given(st.text(min_size=1, max_size=10))
    @settings(max_examples=50, deadline=None)
    def test_short_output_scores_high(self, text):
        result = token_efficiency(inputs="a" * 100, outputs=text, expectations=None)
        assert result.value >= 0.5

    @given(st.text(), st.text())
    @settings(max_examples=100, deadline=None)
    def test_never_raises(self, inp, out):
        result = token_efficiency(inputs=inp, outputs=out, expectations=None)
        assert result is not None

    @given(st.text(min_size=0, max_size=5))
    @settings(max_examples=50, deadline=None)
    def test_deterministic(self, text):
        r1 = token_efficiency(inputs="test", outputs=text, expectations=None)
        r2 = token_efficiency(inputs="test", outputs=text, expectations=None)
        assert r1.value == r2.value
