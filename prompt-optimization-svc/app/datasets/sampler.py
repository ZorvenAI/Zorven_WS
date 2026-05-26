"""Golden dataset sampler with stratified selection and size validation.

When dataset > max, stratified sampling preserves diversity.
When dataset < min, raises InsufficientDatasetError.
"""

import logging
from collections import defaultdict

from app.datasets.golden_seed import GoldenExample

logger = logging.getLogger(__name__)


class InsufficientDatasetError(Exception):
    """Raised when the dataset has fewer examples than the minimum required."""

    def __init__(self, actual: int, minimum: int):
        self.actual = actual
        self.minimum = minimum
        super().__init__(
            f"Insufficient golden dataset: {actual} examples available, "
            f"minimum {minimum} required. Add more examples before "
            f"running optimization."
        )


def validate_dataset_size(examples: list, min_size: int) -> None:
    """Validate that the dataset meets the minimum size requirement.

    Args:
        examples: List of golden examples.
        min_size: Minimum required count.

    Raises:
        InsufficientDatasetError: If len(examples) < min_size (AC-1).
    """
    if len(examples) < min_size:
        raise InsufficientDatasetError(actual=len(examples), minimum=min_size)


def select_golden_examples(
    examples: list[GoldenExample],
    max_size: int,
) -> list[GoldenExample]:
    """Select up to max_size examples using stratified sampling.

    When len(examples) <= max_size, returns all examples.
    When len(examples) > max_size, performs stratified sampling by
    (industry, brand_maturity) to preserve diversity (AC-2).

    Args:
        examples: Full list of golden examples.
        max_size: Maximum number to return.

    Returns:
        List of at most max_size GoldenExamples.
    """
    if not examples:
        return []

    if len(examples) <= max_size:
        return list(examples)

    # Group by (industry, brand_maturity) for stratified sampling
    groups: dict[tuple[str, str], list[GoldenExample]] = defaultdict(list)
    for ex in examples:
        industry = ex.metadata_extra.get("industry", "unknown")
        maturity = ex.metadata_extra.get("brand_maturity", "unknown")
        groups[(industry, maturity)].append(ex)

    # Round-robin select from each group
    selected: list[GoldenExample] = []
    group_keys = sorted(groups.keys())
    group_indices = {k: 0 for k in group_keys}

    while len(selected) < max_size:
        added_this_round = False
        for key in group_keys:
            if len(selected) >= max_size:
                break
            idx = group_indices[key]
            if idx < len(groups[key]):
                selected.append(groups[key][idx])
                group_indices[key] = idx + 1
                added_this_round = True
        if not added_this_round:
            break

    return selected
