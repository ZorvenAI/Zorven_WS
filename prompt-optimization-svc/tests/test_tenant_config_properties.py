"""Hypothesis property tests for tenant TTL clamping (US-011)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.cache.tenant_config import DEFAULT_TTL, MAX_TTL, MIN_TTL, clamp_ttl


class TestClampTTLProperties:

    @given(ttl=st.integers(min_value=-10000, max_value=100000))
    @hyp_settings(max_examples=100)
    def test_result_always_in_range(self, ttl):
        """Output is always within [MIN_TTL, MAX_TTL]."""
        result = clamp_ttl(ttl)
        assert MIN_TTL <= result <= MAX_TTL

    @given(ttl=st.integers(min_value=MIN_TTL, max_value=MAX_TTL))
    @hyp_settings(max_examples=50)
    def test_within_range_passes_through(self, ttl):
        """Values within range are returned unchanged."""
        assert clamp_ttl(ttl) == ttl

    @given(ttl=st.integers(max_value=MIN_TTL - 1))
    @hyp_settings(max_examples=30)
    def test_below_min_clamped(self, ttl):
        """Values below MIN_TTL are clamped to MIN_TTL."""
        assert clamp_ttl(ttl) == MIN_TTL

    @given(ttl=st.integers(min_value=MAX_TTL + 1))
    @hyp_settings(max_examples=30)
    def test_above_max_clamped(self, ttl):
        """Values above MAX_TTL are clamped to MAX_TTL."""
        assert clamp_ttl(ttl) == MAX_TTL

    @given(a=st.integers(min_value=MIN_TTL, max_value=MAX_TTL),
           b=st.integers(min_value=MIN_TTL, max_value=MAX_TTL))
    @hyp_settings(max_examples=30)
    def test_monotonic_within_range(self, a, b):
        """If a <= b within range, clamp(a) <= clamp(b)."""
        if a <= b:
            assert clamp_ttl(a) <= clamp_ttl(b)
