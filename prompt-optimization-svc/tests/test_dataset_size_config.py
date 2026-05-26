"""Unit tests for configurable golden dataset size (US-029)."""

import pytest

from app.cache.tenant_config import (
    DEFAULT_DATASET_SIZE,
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


def _make_example(industry="SaaS/Technology", maturity="new", idx=0):
    return GoldenExample(
        prompt_name=f"zorven-wf1-mra-system",
        agent_code="mra",
        input_context={"context_brand_name": f"Brand{idx}"},
        expected_output=f"Output {idx}",
        source="manual",
        metadata_extra={"industry": industry, "brand_maturity": maturity},
    )


class TestClampDatasetSize:
    def test_below_min(self):
        assert clamp_dataset_size(1) == MIN_DATASET_SIZE

    def test_above_max(self):
        assert clamp_dataset_size(100) == MAX_DATASET_SIZE

    def test_in_range(self):
        assert clamp_dataset_size(25) == 25

    def test_at_min_boundary(self):
        assert clamp_dataset_size(3) == 3

    def test_at_max_boundary(self):
        assert clamp_dataset_size(50) == 50

    def test_zero(self):
        assert clamp_dataset_size(0) == MIN_DATASET_SIZE

    def test_negative(self):
        assert clamp_dataset_size(-5) == MIN_DATASET_SIZE


class TestConstants:
    def test_default_size(self):
        assert DEFAULT_DATASET_SIZE == 10

    def test_min_size(self):
        assert MIN_DATASET_SIZE == 3

    def test_max_size(self):
        assert MAX_DATASET_SIZE == 50


class TestValidateDatasetSize:
    """AC-1: Optimization run aborts when dataset < min."""

    def test_below_min_raises(self):
        with pytest.raises(InsufficientDatasetError) as exc_info:
            validate_dataset_size([1, 2], min_size=3)
        assert exc_info.value.actual == 2
        assert exc_info.value.minimum == 3

    def test_at_min_passes(self):
        validate_dataset_size([1, 2, 3], min_size=3)  # Should not raise

    def test_above_min_passes(self):
        validate_dataset_size([1, 2, 3, 4, 5], min_size=3)

    def test_empty_raises(self):
        with pytest.raises(InsufficientDatasetError):
            validate_dataset_size([], min_size=3)

    def test_error_message_clear(self):
        with pytest.raises(
            InsufficientDatasetError, match="Insufficient golden dataset"
        ):
            validate_dataset_size([1], min_size=3)

    def test_error_includes_counts(self):
        with pytest.raises(InsufficientDatasetError, match="1 examples.*minimum 3"):
            validate_dataset_size([1], min_size=3)


class TestSelectGoldenExamples:
    """AC-2: When dataset > max, stratified sampling selects max."""

    def test_below_max_returns_all(self):
        examples = [_make_example(idx=i) for i in range(5)]
        result = select_golden_examples(examples, max_size=10)
        assert len(result) == 5

    def test_at_max_returns_all(self):
        examples = [_make_example(idx=i) for i in range(10)]
        result = select_golden_examples(examples, max_size=10)
        assert len(result) == 10

    def test_above_max_returns_exactly_max(self):
        examples = [_make_example(idx=i) for i in range(60)]
        result = select_golden_examples(examples, max_size=50)
        assert len(result) == 50

    def test_stratified_preserves_diversity(self):
        industries = ["SaaS/Technology", "Healthcare/Wellness", "Financial Services"]
        examples = []
        for i, ind in enumerate(industries):
            for j in range(20):
                examples.append(_make_example(industry=ind, idx=i * 20 + j))
        result = select_golden_examples(examples, max_size=9)
        result_industries = {e.metadata_extra["industry"] for e in result}
        # All 3 industries should be represented
        assert len(result_industries) == 3

    def test_empty_list_returns_empty(self):
        result = select_golden_examples([], max_size=10)
        assert result == []

    def test_single_example(self):
        examples = [_make_example()]
        result = select_golden_examples(examples, max_size=10)
        assert len(result) == 1

    def test_stratified_by_maturity(self):
        examples = []
        for maturity in ["new", "emerging", "established"]:
            for i in range(10):
                examples.append(_make_example(maturity=maturity, idx=i))
        result = select_golden_examples(examples, max_size=6)
        maturities = {e.metadata_extra["brand_maturity"] for e in result}
        assert len(maturities) >= 2  # At least 2 maturities represented

    def test_returns_list_not_generator(self):
        examples = [_make_example(idx=i) for i in range(5)]
        result = select_golden_examples(examples, max_size=10)
        assert isinstance(result, list)
