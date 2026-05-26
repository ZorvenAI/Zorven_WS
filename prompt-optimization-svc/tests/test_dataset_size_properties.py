"""Hypothesis property tests for dataset size configuration (US-029)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.cache.tenant_config import (
    MAX_DATASET_SIZE,
    MIN_DATASET_SIZE,
    clamp_dataset_size,
)
from app.datasets.golden_seed import GoldenExample
from app.datasets.sampler import (
    InsufficientDatasetError,
    select_golden_examples,
    validate_dataset_size,
)


def _make_example(idx=0):
    return GoldenExample(
        prompt_name="zorven-wf1-mra-system",
        agent_code="mra",
        input_context={"context_brand_name": f"Brand{idx}"},
        expected_output=f"Output {idx}",
        source="manual",
        metadata_extra={"industry": "SaaS/Technology", "brand_maturity": "new"},
    )


class TestClampProperties:
    @given(st.integers(min_value=-1000, max_value=1000))
    @settings(max_examples=100, deadline=None)
    def test_always_in_range(self, size):
        result = clamp_dataset_size(size)
        assert MIN_DATASET_SIZE <= result <= MAX_DATASET_SIZE

    @given(st.integers(min_value=MIN_DATASET_SIZE, max_value=MAX_DATASET_SIZE))
    @settings(max_examples=50, deadline=None)
    def test_in_range_unchanged(self, size):
        assert clamp_dataset_size(size) == size


class TestSelectProperties:
    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_never_exceeds_max(self, max_size):
        examples = [_make_example(idx=i) for i in range(200)]
        result = select_golden_examples(examples, max_size=max_size)
        assert len(result) <= max_size

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_never_exceeds_input(self, max_size):
        examples = [_make_example(idx=i) for i in range(5)]
        result = select_golden_examples(examples, max_size=max_size)
        assert len(result) <= len(examples)


class TestValidateProperties:
    @given(st.integers(min_value=3, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_at_or_above_min_never_raises(self, count):
        examples = list(range(count))
        validate_dataset_size(examples, min_size=3)  # Should not raise
