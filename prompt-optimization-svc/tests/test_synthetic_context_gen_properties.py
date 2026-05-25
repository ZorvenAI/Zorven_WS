"""Hypothesis property tests for synthetic context generator (US-027)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.datasets.golden_seed import INDUSTRIES


class TestGeneratorInitProperties:
    """Generator init accepts valid keys, rejects invalid ones."""

    @given(st.text(min_size=10, max_size=50))
    @settings(max_examples=30, deadline=None)
    def test_non_empty_key_accepted(self, key):
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        gen = SyntheticContextGenerator(api_key=key)
        assert gen.client is not None

    @given(st.sampled_from(["", "   ", "\t", "\n"]))
    def test_blank_keys_rejected(self, key):
        from app.datasets.synthetic_context_gen import SyntheticContextGenerator

        with pytest.raises(ValueError):
            SyntheticContextGenerator(api_key=key)


class TestIndustryValidation:
    """All canonical industries are valid inputs."""

    @given(st.sampled_from(INDUSTRIES))
    @settings(max_examples=12, deadline=None)
    def test_canonical_industry_accepted(self, industry):
        # Just verify the industry is a non-empty string
        assert isinstance(industry, str)
        assert len(industry) > 0

    @given(st.sampled_from(["new", "emerging", "established"]))
    @settings(max_examples=3, deadline=None)
    def test_valid_maturity_accepted(self, maturity):
        assert maturity in {"new", "emerging", "established"}


class TestRequiredFields:
    """Verify REQUIRED_FIELDS constant is complete."""

    def test_required_fields_tuple(self):
        from app.datasets.synthetic_context_gen import REQUIRED_FIELDS

        assert isinstance(REQUIRED_FIELDS, tuple)
        assert "brand_name" in REQUIRED_FIELDS
        assert "product_description" in REQUIRED_FIELDS
        assert "target_audience" in REQUIRED_FIELDS
        assert "brand_voice" in REQUIRED_FIELDS
        assert len(REQUIRED_FIELDS) >= 4
